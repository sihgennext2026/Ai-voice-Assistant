import asyncio
import json
import logging
import threading
import time
import wave
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

import numpy as np
import sounddevice as sd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_settings
from knowledge.base import get_knowledge
from livelihood.llm import LLMClient
from livelihood.session import LivelihoodSession, demo_script_lines
from location.service import LocationService
from main import VoiceAgent

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("API")

DEMO_AUDIO_DIR = Path(__file__).resolve().parent / "demo_audio"
LEVEL_INTERVAL_S = 0.08

app = FastAPI(title="Livelihood Guidance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

voice_agent: Optional["APIVoiceAgent"] = None
event_queue: Queue = Queue()


def emit(msg: dict):
    """Thread-safe: called from agent threads, drained by the async broadcaster."""
    event_queue.put(msg)


class APIVoiceAgent(VoiceAgent):
    """Voice loop (mic -> ASR -> livelihood session -> TTS) driven from the web UI."""

    def __init__(self, session: LivelihoodSession):
        super().__init__()
        self.session = session
        self.should_stop = True
        self.cancelled = threading.Event()
        self.active = False
        self.busy = False
        self._pending_text: Queue = Queue()
        self._last_level = 0.0
        self._loop_thread: Optional[threading.Thread] = None

    # ── control ──────────────────────────────────────────────────────────────
    def check_quit(self):
        return self.should_stop

    def _interrupt_recording(self):
        return self.should_stop or not self._pending_text.empty()

    def start(self) -> bool:
        if self.active or self.busy:
            return False
        self.should_stop = False
        self.cancelled.clear()
        self.active = True
        self._loop_thread = threading.Thread(target=self.run, daemon=True)
        self._loop_thread.start()
        return True

    def stop(self):
        self.should_stop = True
        self.cancelled.set()
        try:
            self.tts.stop()
        except Exception:
            pass

    def submit_text(self, text: str):
        """Typed input. Handled by the voice loop if running, otherwise on a worker thread."""
        if self.active:
            self._pending_text.put(text)
        elif not self.busy:
            threading.Thread(target=self._single_turn, args=(text,), daemon=True).start()

    def _single_turn(self, text: str):
        self.busy = True
        self.cancelled.clear()
        try:
            self.process_turn(text)
        finally:
            self.busy = False
            emit({"type": "status", "status": "idle"})

    def _on_level(self, rms: float):
        now = time.monotonic()
        if now - self._last_level >= LEVEL_INTERVAL_S:
            self._last_level = now
            emit({"type": "level", "value": round(min(1.0, rms * 12), 3)})

    # ── voice loop ───────────────────────────────────────────────────────────
    def run(self):
        emit({"type": "agent_active", "active": True})
        logger.info("Voice loop started")
        try:
            while not self.should_stop:
                try:
                    self.process_turn(self._pending_text.get_nowait())
                    continue
                except Empty:
                    pass

                emit({"type": "status", "status": "listening"})
                audio = self.recorder.record_until_silence(
                    threshold=0.005,
                    silence_duration=1.0,
                    interrupt_check=self._interrupt_recording,
                    vad_function=None,
                    level_callback=self._on_level,
                )
                emit({"type": "level", "value": 0})
                if self.should_stop or audio is None or len(audio) == 0:
                    continue
                text = self.transcribe(audio)
                if text:
                    self.process_turn(text)
        except Exception:
            logger.exception("Voice loop crashed")
        finally:
            self.active = False
            emit({"type": "status", "status": "idle"})
            emit({"type": "agent_active", "active": False})
            logger.info("Voice loop stopped")

    def transcribe(self, audio: np.ndarray) -> str:
        emit({"type": "status", "status": "transcribing"})
        try:
            segments, _ = self.asr_model.transcribe(audio)
            return " ".join(s.text for s in segments).strip()
        except Exception:
            logger.exception("ASR failed")
            return ""

    def process_turn(self, text: str):
        try:
            self.speak_and_wait(lambda: self.session.handle_turn(text, emit, self.tts.synthesize))
        except Exception:
            logger.exception("Turn failed")

    def speak_and_wait(self, produce):
        produce()
        self.tts.end_turn()
        if self.tts.is_busy:
            emit({"type": "status", "status": "responding"})
            while self.tts.is_busy and not self.cancelled.is_set():
                time.sleep(0.05)

    # ── recorded sample case (real ASR on recorded beneficiary audio) ────────
    def run_sample_case(self):
        self.busy = True
        self.cancelled.clear()
        try:
            self.session.reset()
            emit(self.session.snapshot())
            case = get_knowledge().demo_cases.get(settings.demo_case_id, {})
            for i, fallback_text in enumerate(case.get("sample_utterances", []), start=1):
                if self.cancelled.is_set():
                    break
                audio = self._play_recording(DEMO_AUDIO_DIR / f"utterance_{i}.wav")
                if self.cancelled.is_set():
                    break
                text = self.transcribe(audio) if audio is not None else ""
                self.process_turn(text or fallback_text)
                time.sleep(0.4)
        except Exception:
            logger.exception("Sample case failed")
        finally:
            self.busy = False
            emit({"type": "status", "status": "idle"})

    def _play_recording(self, path: Path) -> Optional[np.ndarray]:
        """Plays the recorded beneficiary utterance aloud and returns it as 16 kHz float32 audio."""
        if not path.exists():
            return None
        with wave.open(str(path)) as w:
            rate = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        emit({"type": "status", "status": "listening"})
        try:
            sd.play(pcm, samplerate=rate)
            chunk = int(rate * LEVEL_INTERVAL_S)
            for start in range(0, len(pcm), chunk):
                if self.cancelled.is_set():
                    sd.stop()
                    return None
                block = pcm[start:start + chunk].astype(np.float32) / 32768
                emit({"type": "level", "value": round(min(1.0, float(np.sqrt(np.mean(block ** 2))) * 12), 3)})
                time.sleep(LEVEL_INTERVAL_S)
            sd.wait()
        except Exception:
            logger.warning("Could not play sample audio; transcribing silently")
        emit({"type": "level", "value": 0})
        audio = pcm.astype(np.float32) / 32768
        if rate != 16000:
            from scipy.signal import resample_poly
            audio = resample_poly(audio, 16000, rate).astype(np.float32)
        return audio


# ── WebSocket broadcast ──────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await websocket.send_json(capabilities())
        if voice_agent:
            await websocket.send_json(voice_agent.session.snapshot())
            await websocket.send_json({"type": "agent_active", "active": voice_agent.active})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


def capabilities() -> dict:
    return {
        "type": "capabilities",
        "demo_mode": settings.demo_mode,
        "llm": voice_agent.session.llm.provider_names if voice_agent else [],
        "tts": voice_agent.tts.provider if voice_agent else None,
        "asr": settings.whisper_model,
        "ready": voice_agent is not None,
    }


@app.on_event("startup")
async def startup_event():
    global voice_agent
    kb = get_knowledge()
    session = LivelihoodSession(settings, kb, LLMClient(settings), LocationService(settings, kb))
    try:
        voice_agent = APIVoiceAgent(session)
        logger.info("Agent ready. Services: %s", settings.capability_report())
        threading.Thread(target=prewarm_demo_speech, args=(voice_agent, kb), daemon=True).start()
    except SystemExit:
        logger.error("Voice components failed to initialise")
    asyncio.create_task(consume_queue())


def prewarm_demo_speech(agent: "APIVoiceAgent", kb):
    """Caches the deterministic demo lines so they play instantly (and offline) during the demo."""
    lines = demo_script_lines(settings, kb, agent.session.location)
    if lines:
        ready = sum(agent.tts.prefetch(line) for line in lines)
        logger.info("Demo speech cache: %d/%d lines ready (%s)", ready, len(lines), agent.tts.provider)


async def consume_queue():
    while True:
        try:
            msg = event_queue.get_nowait()
            await manager.broadcast(msg)
        except Empty:
            await asyncio.sleep(0.02)
        except Exception as exc:
            logger.error("Queue error: %s", exc)
            await asyncio.sleep(0.1)


# ── REST ─────────────────────────────────────────────────────────────────────
class TextInput(BaseModel):
    text: str


def _not_ready():
    return {"status": "error", "message": "Agent not initialised"}


@app.get("/health")
async def health():
    return {"status": "ok", "services": settings.capability_report(), **capabilities()}


@app.post("/agent/start")
async def start_agent():
    if voice_agent is None:
        return _not_ready()
    return {"status": "started" if voice_agent.start() else "already_running"}


@app.post("/agent/stop")
async def stop_agent():
    if voice_agent is None:
        return _not_ready()
    voice_agent.stop()
    return {"status": "stopped"}


@app.get("/agent/status")
async def agent_status():
    return {"active": bool(voice_agent and voice_agent.active)}


@app.get("/session")
async def get_session():
    return voice_agent.session.snapshot() if voice_agent else _not_ready()


@app.post("/session/reset")
async def reset_session():
    if voice_agent is None:
        return _not_ready()
    voice_agent.stop()
    voice_agent.session.reset()
    emit(voice_agent.session.snapshot())
    return {"status": "reset"}


@app.post("/session/text")
async def session_text(body: TextInput):
    if voice_agent is None:
        return _not_ready()
    voice_agent.submit_text(body.text)
    return {"status": "accepted"}


@app.post("/demo/run")
async def run_demo():
    if voice_agent is None:
        return _not_ready()
    if voice_agent.active or voice_agent.busy:
        return {"status": "busy"}
    voice_agent.busy = True
    threading.Thread(target=voice_agent.run_sample_case, daemon=True).start()
    return {"status": "started"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            action = data.get("action")
            if not voice_agent:
                continue
            if action == "user_text" and str(data.get("text", "")).strip():
                voice_agent.submit_text(str(data["text"]).strip())
            elif action == "stop_speaking":
                voice_agent.tts.stop()
            elif action == "reset":
                voice_agent.stop()
                voice_agent.session.reset()
                emit(voice_agent.session.snapshot())
    except WebSocketDisconnect:
        manager.disconnect(websocket)

"""Speech output: ElevenLabs when configured, local Piper otherwise. Same interface as PiperTTS."""
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import requests

from config import BASE_DIR, Settings
from tts.tts import PiperTTS

logger = logging.getLogger(__name__)
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
MAX_ELEVENLABS_FAILURES = 2
CACHE_DIR = BASE_DIR / "demo_audio" / "tts_cache"


class SpeechService:
    """Both engines emit 22.05 kHz int16 PCM, so ElevenLabs audio reuses Piper's playback queue.

    ElevenLabs results are cached on disk by (voice, model, text): deterministic demo lines play
    instantly and keep working if the ElevenLabs API later becomes unavailable.
    """

    def __init__(self, settings: Settings, models_dir: str, cache_dir: Path = CACHE_DIR):
        self.settings = settings
        self.piper = PiperTTS(models_dir)
        self.cache_dir = cache_dir
        self._memory: Dict[str, np.ndarray] = {}
        self._elevenlabs_failures = 0
        self.last_provider: Optional[str] = None

    @property
    def valid(self) -> bool:
        return self.piper.valid or self.elevenlabs_active

    @property
    def elevenlabs_active(self) -> bool:
        return self.settings.elevenlabs_enabled and self._elevenlabs_failures < MAX_ELEVENLABS_FAILURES

    @property
    def provider(self) -> str:
        return "elevenlabs" if self.elevenlabs_active else "piper"

    def _cache_key(self, text: str) -> str:
        raw = f"{self.settings.elevenlabs_voice_id}|{self.settings.elevenlabs_model}|{text}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cached(self, key: str) -> Optional[np.ndarray]:
        if key in self._memory:
            return self._memory[key]
        path = self.cache_dir / f"{key}.pcm"
        if path.exists():
            audio = np.frombuffer(path.read_bytes(), dtype=np.int16)
            self._memory[key] = audio
            return audio
        return None

    def _store(self, key: str, audio: np.ndarray):
        self._memory[key] = audio
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.pcm").write_bytes(audio.tobytes())
        except OSError:
            logger.warning("Could not write TTS cache")

    def _elevenlabs(self, text: str) -> Optional[np.ndarray]:
        if not self.settings.elevenlabs_enabled:
            return None
        key = self._cache_key(text)
        cached = self._cached(key)
        if cached is not None:
            return cached
        if not self.elevenlabs_active:
            return None
        try:
            r = requests.post(
                ELEVENLABS_URL.format(voice_id=self.settings.elevenlabs_voice_id),
                params={"output_format": "pcm_22050"},
                headers={"xi-api-key": self.settings.elevenlabs_api_key},
                json={
                    "text": text,
                    "model_id": self.settings.elevenlabs_model,
                    "voice_settings": {"stability": 0.55, "similarity_boost": 0.75},
                },
                timeout=8,
            )
            r.raise_for_status()
            if len(r.content) < 2:
                raise ValueError("empty audio")
            self._elevenlabs_failures = 0
            audio = np.frombuffer(r.content[: len(r.content) // 2 * 2], dtype=np.int16)
            self._store(key, audio)
            return audio
        except Exception as exc:
            self._elevenlabs_failures += 1
            logger.warning("ElevenLabs TTS failed (%s); using Piper", type(exc).__name__)
            return None

    def prefetch(self, text: str) -> bool:
        """Synthesise into the cache without playing. Returns True if ElevenLabs audio is ready."""
        return self._elevenlabs(text.strip()) is not None

    def synthesize(self, text: str):
        text = text.strip()
        if not text:
            return
        audio = self._elevenlabs(text)
        if audio is not None:
            self.piper.audio_queue.put(audio)
            self.piper.start_playback()
            self.last_provider = "elevenlabs"
            return
        self.piper.synthesize(text)
        self.last_provider = "piper"

    def end_turn(self):
        self.piper.end_turn()

    def stop(self):
        self.piper.stop()

    @property
    def is_busy(self) -> bool:
        return self.piper.is_busy

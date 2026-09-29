"""Typed application configuration. The only module that reads environment variables."""
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def normalize_whisper_model(value: Optional[str]) -> str:
    """Accept either a faster-whisper model name or a HuggingFace URL like .../openai/whisper-large-v3."""
    if not value:
        return "distil-small.en"
    match = re.search(r"huggingface\.co/([^/\s]+/[^/\s?#]+)", value)
    if match:
        repo = match.group(1)
        openai_match = re.fullmatch(r"openai/whisper-(.+)", repo)
        # faster-whisper resolves short names like "large-v3" to CTranslate2 conversions.
        return openai_match.group(1) if openai_match else repo
    return value


class Settings(BaseModel):
    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"

    llm_provider: str = "openrouter"
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "qwen/qwen-plus-2025-07-28"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-flash-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048
    llm_timeout_s: float = 12.0

    asr_provider: str = "whisper"
    whisper_model: str = "distil-small.en"
    hf_token: Optional[str] = None

    tts_provider: str = "elevenlabs"
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_model: str = "eleven_turbo_v2_5"

    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    openrouteservice_api_key: Optional[str] = None
    google_translate_api_key: Optional[str] = None

    demo_mode: bool = True
    demo_case_id: str = "demo-tailoring-001"
    log_level: str = "INFO"

    @property
    def elevenlabs_enabled(self) -> bool:
        return self.tts_provider == "elevenlabs" and bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    def capability_report(self) -> dict:
        """Configured/missing status only. Never includes secret values."""
        def status(ok: bool) -> str:
            return "configured" if ok else "missing"

        return {
            "OpenRouter": status(bool(self.openrouter_api_key)),
            "Gemini": status(bool(self.gemini_api_key)),
            "ElevenLabs": status(bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)),
            "Whisper": f"configured ({self.whisper_model})",
            "OpenRouteService": status(bool(self.openrouteservice_api_key)),
            "Google Translate": status(bool(self.google_translate_api_key)),
            "DEMO_MODE": str(self.demo_mode).lower(),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=_env("APP_ENV", "development"),
        frontend_url=_env("NEXT_PUBLIC_APP_URL", "http://localhost:5173"),
        llm_provider=_env("LLM_PROVIDER", "openrouter"),
        openrouter_api_key=_env("OPENROUTER_API_KEY"),
        openrouter_model=_env("OPENROUTER_MODEL", "qwen/qwen-plus-2025-07-28"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-flash-latest"),
        llm_temperature=float(_env("LLM_TEMPERATURE", "0.2")),
        llm_max_tokens=int(_env("LLM_MAX_TOKENS", "2048")),
        llm_timeout_s=float(_env("LLM_TIMEOUT_S", "12")),
        asr_provider=_env("ASR_PROVIDER", "whisper"),
        whisper_model=normalize_whisper_model(_env("WHISPER_MODEL")),
        hf_token=_env("HF_TOKEN"),
        tts_provider=_env("TTS_PROVIDER", "elevenlabs"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID"),
        elevenlabs_model=_env("ELEVENLABS_MODEL", "eleven_turbo_v2_5"),
        nominatim_base_url=_env("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"),
        overpass_api_url=_env("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter"),
        openrouteservice_api_key=_env("OPENROUTESERVICE_API_KEY"),
        google_translate_api_key=_env("GOOGLE_TRANSLATE_API_KEY"),
        demo_mode=_env_bool("DEMO_MODE", True),
        demo_case_id=_env("DEMO_CASE_ID", "demo-tailoring-001"),
        log_level=_env("LOG_LEVEL", "INFO"),
    )

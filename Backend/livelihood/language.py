"""Supported conversation languages and language detection."""
import re
from typing import Dict, Iterable, Optional

# code -> (English name, native name, Unicode script range or None for Latin)
LANGUAGES: Dict[str, dict] = {
    "en": {"name": "English", "native": "English", "script": None},
    "hi": {"name": "Hindi", "native": "हिन्दी", "script": r"[ऀ-ॿ]"},
    "mr": {"name": "Marathi", "native": "मराठी", "script": r"[ऀ-ॿ]"},
    "bn": {"name": "Bengali", "native": "বাংলা", "script": r"[ঀ-৿]"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "script": r"[઀-૿]"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "script": r"[਀-੿]"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "script": r"[஀-௿]"},
    "te": {"name": "Telugu", "native": "తెలుగు", "script": r"[ఀ-౿]"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "script": r"[ಀ-೿]"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "script": r"[ഀ-ൿ]"},
}

# Common romanised-Hindi words: typed Hinglish is treated as Hindi.
_HINGLISH = re.compile(
    r"\b(mujhe|mera|meri|mere|main|hum|nahi|nahin|haan|aata|aati|chahiye|kaam|silai|sakti|sakta|"
    r"gaon|gaanv|paisa|kamai|aamdani|seekha|sikha|kya|hai|hoon|hu)\b"
)


def name(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES["en"])["name"]


def native(code: str) -> str:
    return LANGUAGES.get(code, LANGUAGES["en"])["native"]


def is_supported(code: Optional[str]) -> bool:
    return code in LANGUAGES


def detect_text(text: str, allowed: Iterable[str]) -> str:
    """Script-based detection for typed input. Devanagari defaults to Hindi (Marathi if Hindi is not allowed)."""
    allowed = list(allowed)
    for code in allowed:
        script = LANGUAGES[code]["script"]
        if script and code != "mr" and len(re.findall(script, text)) >= 2:
            return code
    if "mr" in allowed and len(re.findall(LANGUAGES["mr"]["script"], text)) >= 2:
        return "mr"
    if "hi" in allowed and len(_HINGLISH.findall(text.lower())) >= 2:
        return "hi"
    return "en" if "en" in allowed else allowed[0]


def pick_asr_language(detected: str, probabilities: Optional[list], allowed: Iterable[str]) -> Optional[str]:
    """If Whisper detected a language outside the allowed set, return the most likely allowed one
    (so the caller can re-transcribe). Returns None when the detected language is fine."""
    allowed = set(allowed)
    if detected in allowed:
        return None
    for code, _prob in sorted(probabilities or [], key=lambda p: -p[1]):
        if code in allowed:
            return code
    return "en" if "en" in allowed else next(iter(allowed))

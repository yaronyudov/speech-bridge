"""Language codes and per-provider language/voice mappings for EN, HE, AR."""

from speech_engine.core.exceptions import UnsupportedLanguageError

# --------------------------------------------------------------------------- #
# Canonical language codes (ISO 639-1)
# --------------------------------------------------------------------------- #
LANGUAGE_EN = "en"
LANGUAGE_HE = "he"
LANGUAGE_AR = "ar"

SUPPORTED_LANGUAGES = frozenset({LANGUAGE_EN, LANGUAGE_HE, LANGUAGE_AR})
DEFAULT_LANGUAGE = LANGUAGE_EN

LANGUAGE_NAMES: dict[str, str] = {
    LANGUAGE_EN: "English",
    LANGUAGE_HE: "Hebrew",
    LANGUAGE_AR: "Arabic",
}

# Legacy / alternate codes accepted from clients and normalized.
_LANGUAGE_ALIASES: dict[str, str] = {
    "iw": LANGUAGE_HE,  # deprecated ISO 639-1 code for Hebrew
}

# --------------------------------------------------------------------------- #
# STT mappings
# --------------------------------------------------------------------------- #
# faster-whisper / OpenAI Whisper accept bare ISO 639-1 codes.
WHISPER_LANGUAGES: dict[str, str] = {
    LANGUAGE_EN: "en",
    LANGUAGE_HE: "he",
    LANGUAGE_AR: "ar",
}

# Azure Speech-to-Text recognition locales.
AZURE_STT_LOCALES: dict[str, str] = {
    LANGUAGE_EN: "en-US",
    LANGUAGE_HE: "he-IL",
    LANGUAGE_AR: "ar-SA",
}

# Amazon Transcribe (streaming) language codes.
AWS_TRANSCRIBE_LANGUAGES: dict[str, str] = {
    LANGUAGE_EN: "en-US",
    LANGUAGE_HE: "he-IL",
    LANGUAGE_AR: "ar-SA",
}

# --------------------------------------------------------------------------- #
# TTS voice mappings
# --------------------------------------------------------------------------- #
# Azure Neural TTS voices.
AZURE_TTS_VOICES: dict[str, str] = {
    LANGUAGE_EN: "en-US-JennyNeural",
    LANGUAGE_HE: "he-IL-HilaNeural",
    LANGUAGE_AR: "ar-SA-ZariyahNeural",
}

# edge-tts exposes the same Microsoft neural voice catalogue without keys.
EDGE_TTS_VOICES: dict[str, str] = {
    LANGUAGE_EN: "en-US-JennyNeural",
    LANGUAGE_HE: "he-IL-HilaNeural",
    LANGUAGE_AR: "ar-SA-ZariyahNeural",
}

# Amazon Polly voices. NOTE: Polly currently offers no Hebrew voice —
# requesting `he` with the AWS TTS engine raises UnsupportedLanguageError.
POLLY_VOICES: dict[str, dict[str, str]] = {
    LANGUAGE_EN: {"voice_id": "Joanna", "engine": "neural", "language_code": "en-US"},
    LANGUAGE_AR: {"voice_id": "Hala", "engine": "neural", "language_code": "ar-AE"},
    # Standard-engine fallback for Arabic (Modern Standard Arabic):
    # {"voice_id": "Zeina", "engine": "standard", "language_code": "arb"}
}

# Coqui XTTS v2 supported subset. NOTE: XTTS v2 does not support Hebrew.
COQUI_XTTS_LANGUAGES: dict[str, str] = {
    LANGUAGE_EN: "en",
    LANGUAGE_AR: "ar",
}


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def normalize_language(language: str | None) -> str | None:
    """Normalize a client-supplied language tag to a canonical code.

    ``"he-IL"`` -> ``"he"``, ``"IW"`` -> ``"he"``, ``None``/empty -> ``None``
    (meaning: auto-detect where the engine supports it).

    Raises:
        UnsupportedLanguageError: for any language outside {en, he, ar}.
    """
    if language is None or not str(language).strip():
        return None
    code = str(language).strip().lower().replace("_", "-").split("-")[0]
    code = _LANGUAGE_ALIASES.get(code, code)
    if code not in SUPPORTED_LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported language '{language}'. "
            f"Supported languages: en (English), he (Hebrew), ar (Arabic)."
        )
    return code


def require_language(language: str | None) -> str:
    """Like :func:`normalize_language` but a language MUST be provided."""
    code = normalize_language(language)
    if code is None:
        raise UnsupportedLanguageError(
            "A language is required. Supported languages: en, he, ar."
        )
    return code

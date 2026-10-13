"""Tests for language constants, RTL detection, and BiDi terminal layout."""

import pytest

from scripts.compare_hebrew_models import compute_rms, format_hebrew_line, rms_bars
from speech_engine.core.constants import (
    EDGE_TTS_VOICES,
    LANGUAGE_AR,
    LANGUAGE_EN,
    LANGUAGE_HE,
    RTL_LANGUAGES,
    SUPPORTED_LANGUAGES,
    is_rtl_language,
    normalize_language,
    require_language,
)
from speech_engine.core.exceptions import UnsupportedLanguageError


def test_is_rtl_language():
    # True for Hebrew and Arabic variants
    assert is_rtl_language("he") is True
    assert is_rtl_language("HE") is True
    assert is_rtl_language("he-IL") is True
    assert is_rtl_language("iw") is True  # Legacy ISO 639-1 code
    assert is_rtl_language("iw-IL") is True
    assert is_rtl_language("ar") is True
    assert is_rtl_language("AR") is True
    assert is_rtl_language("ar-SA") is True
    assert is_rtl_language("ar-EG") is True

    # False for LTR languages and non-languages
    assert is_rtl_language("en") is False
    assert is_rtl_language("en-US") is False
    assert is_rtl_language("fr") is False
    assert is_rtl_language("de") is False
    assert is_rtl_language("") is False
    assert is_rtl_language("   ") is False
    assert is_rtl_language(None) is False


def test_rtl_languages_set():
    assert LANGUAGE_HE in RTL_LANGUAGES
    assert LANGUAGE_AR in RTL_LANGUAGES
    assert LANGUAGE_EN not in RTL_LANGUAGES


def test_normalize_language():
    assert normalize_language("he") == "he"
    assert normalize_language("HE") == "he"
    assert normalize_language("iw") == "he"
    assert normalize_language("he-il") == "he"
    assert normalize_language("en-us") == "en"
    assert normalize_language("ar_ae") == "ar"
    assert normalize_language(None) is None

    with pytest.raises(UnsupportedLanguageError):
        normalize_language("es")

    with pytest.raises(UnsupportedLanguageError):
        normalize_language("zh-cn")


def test_require_language():
    assert require_language("he") == "he"
    assert require_language("en") == "en"
    assert require_language("ar") == "ar"

    with pytest.raises(UnsupportedLanguageError):
        require_language(None)

    with pytest.raises(UnsupportedLanguageError):
        require_language("fr")


def test_edge_tts_voices_coverage():
    for lang in SUPPORTED_LANGUAGES:
        assert lang in EDGE_TTS_VOICES
        assert len(EDGE_TTS_VOICES[lang]) > 0


def test_bidi_format_hebrew_line():
    # Empty string
    assert format_hebrew_line("") == ""
    assert format_hebrew_line(None) == ""

    # Non-empty Hebrew text
    text = "שלום עולם"
    res = format_hebrew_line(text, tag="[סופי]", right_align=False)
    assert "[סופי]" in res

    # Right-aligned line
    right_aligned = format_hebrew_line(text, tag="[מתמלל 12ms]", right_align=True)
    assert "[מתמלל 12ms]" in right_aligned

    # Text without tag
    plain = format_hebrew_line(text, tag="", right_align=False)
    assert len(plain) > 0


def test_rms_computation_and_bars():
    import numpy as np

    # Silence
    silence = np.zeros(1600, dtype=np.float32)
    assert compute_rms(silence) == 0.0
    bars_zero = rms_bars(0.0)
    assert len(bars_zero) == 4

    # Signal
    signal = np.full(1600, 0.5, dtype=np.float32)
    rms_val = compute_rms(signal)
    assert rms_val > 1000.0
    bars_active = rms_bars(rms_val)
    assert "█" in bars_active

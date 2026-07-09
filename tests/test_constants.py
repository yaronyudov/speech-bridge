"""Language normalization and per-provider mappings."""

import pytest

from speech_engine.core.constants import (
    POLLY_VOICES,
    SUPPORTED_LANGUAGES,
    normalize_language,
    require_language,
)
from speech_engine.core.exceptions import UnsupportedLanguageError


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("HE", "he"),
        ("he-IL", "he"),
        ("ar_SA", "ar"),
        ("iw", "he"),  # legacy Hebrew code
        (None, None),
        ("", None),
        ("  ", None),
    ],
)
def test_normalize_language(raw, expected):
    assert normalize_language(raw) == expected


@pytest.mark.parametrize("bad", ["fr", "de", "zh", "xx"])
def test_normalize_language_rejects_unsupported(bad):
    with pytest.raises(UnsupportedLanguageError) as exc:
        normalize_language(bad)
    assert exc.value.status_code == 400
    assert exc.value.ws_close_code == 4400


def test_require_language_needs_a_value():
    with pytest.raises(UnsupportedLanguageError):
        require_language(None)
    assert require_language("en") == "en"


def test_supported_languages():
    assert SUPPORTED_LANGUAGES == frozenset({"en", "he", "ar"})


def test_polly_has_no_hebrew():
    # Documents the known gap enforced by the AWS TTS engine.
    assert "he" not in POLLY_VOICES
    assert "en" in POLLY_VOICES and "ar" in POLLY_VOICES

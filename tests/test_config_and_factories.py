"""Configuration parsing, engine factories, and secret resolution no-op."""

import pytest

from speech_engine.core.exceptions import ConfigurationError


def test_defaults(configure_env):
    configure_env()
    from speech_engine.config import get_settings

    s = get_settings()
    assert s.ENABLE_STT and s.ENABLE_TTS
    assert s.STT_ENGINE == "local" and s.TTS_ENGINE == "local"
    assert s.STT_LOCAL_MODEL_SIZE == "large-v3"


def test_api_keys_csv_parsing(configure_env):
    configure_env(API_KEYS="k1, k2 ,k3")
    from speech_engine.config import get_settings

    assert get_settings().API_KEYS == ["k1", "k2", "k3"]


def test_stt_factory_disabled_guard(configure_env):
    configure_env(ENABLE_STT="false")
    from speech_engine.core.stt.factory import get_stt_engine

    with pytest.raises(ConfigurationError):
        get_stt_engine()


def test_stt_factory_returns_singleton(configure_env):
    configure_env(ENABLE_STT="true", STT_ENGINE="local")
    from speech_engine.core.stt.factory import get_stt_engine

    assert get_stt_engine() is get_stt_engine()


def test_tts_factory_selects_backend(configure_env):
    configure_env(ENABLE_TTS="true", TTS_ENGINE="local", TTS_LOCAL_BACKEND="edge")
    from speech_engine.core.tts.factory import get_tts_engine

    engine = get_tts_engine()
    assert engine.name == "local-edge"
    assert engine.file_extension == "mp3"


@pytest.mark.parametrize("engine", ["azure", "openai"])
def test_remote_stt_requires_credentials(configure_env, engine):
    configure_env(ENABLE_STT="true", STT_ENGINE=engine)
    from speech_engine.core.stt.factory import get_stt_engine

    with pytest.raises(ConfigurationError):
        get_stt_engine()


def test_secret_overrides_noop_when_backend_none(configure_env):
    configure_env(SECRETS_BACKEND="none", OPENAI_API_KEY="from-env")
    from speech_engine.config import get_settings
    from speech_engine.core.secrets import apply_secret_overrides

    settings = get_settings()
    apply_secret_overrides(settings)  # must not touch anything
    assert settings.OPENAI_API_KEY == "from-env"

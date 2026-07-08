"""Application configuration manager.

Settings are resolved with the following priority (highest wins):

1. Process environment variables
2. ``.env`` file in the working directory
3. ``config.yaml`` file in the working directory
4. Field defaults declared below

Every setting can therefore be supplied either as an environment variable
(``STT_ENGINE=azure``), a ``.env`` entry, or a ``config.yaml`` key.
"""

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal, Tuple, Type

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Settings(BaseSettings):
    """Central, validated configuration for the whole service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Subsystem toggles (partial modes: STT-only, TTS-only, or both)
    # ------------------------------------------------------------------ #
    ENABLE_STT: bool = True
    ENABLE_TTS: bool = True

    # ------------------------------------------------------------------ #
    # Engine selection (Strategy chosen by the Factory at startup)
    # ------------------------------------------------------------------ #
    STT_ENGINE: Literal["local", "azure", "openai", "aws"] = "local"
    TTS_ENGINE: Literal["local", "azure", "openai", "aws"] = "local"

    # ------------------------------------------------------------------ #
    # Local STT (faster-whisper)
    # ------------------------------------------------------------------ #
    STT_LOCAL_MODEL_SIZE: str = "large-v3"
    # "auto" resolves to cuda when torch/ctranslate2 report an available GPU.
    STT_LOCAL_DEVICE: Literal["auto", "cuda", "cpu"] = "auto"
    # "auto" resolves to float16 on GPU and int8 on CPU.
    STT_LOCAL_COMPUTE_TYPE: Literal[
        "auto", "float16", "int8", "int8_float16", "float32"
    ] = "auto"
    STT_LOCAL_BEAM_SIZE: int = 5

    # ------------------------------------------------------------------ #
    # Live-streaming STT tuning (applies to the rolling-buffer pipelines)
    # ------------------------------------------------------------------ #
    # Minimum seconds of *new* audio accumulated before another local
    # inference pass runs on the rolling buffer.
    STT_STREAM_INFER_INTERVAL_SECONDS: float = 1.5
    # A segment is force-finalized once its buffer reaches this length.
    STT_STREAM_MAX_SEGMENT_SECONDS: float = 12.0
    # int16 RMS energy below which audio is treated as silence.
    STT_STREAM_SILENCE_RMS_THRESHOLD: int = 300
    # Trailing silence of this duration finalizes the current segment.
    STT_STREAM_TRAILING_SILENCE_SECONDS: float = 0.6
    # Pseudo-streaming flush interval used by the OpenAI live adapter.
    STT_STREAM_OPENAI_FLUSH_SECONDS: float = 3.0

    # ------------------------------------------------------------------ #
    # Local TTS
    # ------------------------------------------------------------------ #
    # "edge" (default, zero-cost, excellent he/ar quality) or "coqui"
    # (fully offline XTTS v2 — heavy download; no Hebrew support).
    TTS_LOCAL_BACKEND: Literal["edge", "coqui"] = "edge"
    TTS_COQUI_MODEL_NAME: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    TTS_COQUI_SPEAKER: str = "Ana Florence"

    # ------------------------------------------------------------------ #
    # Azure (Speech Services: STT batch/live + Neural TTS)
    # ------------------------------------------------------------------ #
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""

    # ------------------------------------------------------------------ #
    # OpenAI (Whisper API + TTS)
    # ------------------------------------------------------------------ #
    OPENAI_API_KEY: str = ""
    OPENAI_STT_MODEL: str = "whisper-1"
    OPENAI_TTS_MODEL: str = "tts-1"
    OPENAI_TTS_VOICE: str = "alloy"

    # ------------------------------------------------------------------ #
    # AWS (Amazon Transcribe Streaming + Amazon Polly)
    # ------------------------------------------------------------------ #
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_POLLY_ENGINE: Literal["neural", "standard"] = "neural"

    # ------------------------------------------------------------------ #
    # Server
    # ------------------------------------------------------------------ #
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    # Empty string -> <system temp dir>/speech_engine
    TEMP_DIR: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # env vars > .env > config.yaml > defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    def resolve_temp_dir(self) -> Path:
        """Directory used for uploaded audio and synthesized output files."""
        base = (
            Path(self.TEMP_DIR)
            if self.TEMP_DIR
            else Path(tempfile.gettempdir()) / "speech_engine"
        )
        base.mkdir(parents=True, exist_ok=True)
        return base


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()

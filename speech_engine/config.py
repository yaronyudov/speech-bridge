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
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
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
    # Minimum audio context seconds required before the first inference pass
    # (prevents broken syllables on fractional words; 0.0 allows instant inference in tests).
    STT_STREAM_MIN_CONTEXT_SECONDS: float = 0.0
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
    # Security: API authentication & rate limiting
    # ------------------------------------------------------------------ #
    # When true, every /api/v1 route (and the live-transcribe handshake)
    # requires a valid key in the `X-API-Key` header. Default false so
    # local development stays frictionless; enable in production.
    ENABLE_AUTH: bool = False
    # Accepted API keys. Provide as a comma-separated string or JSON list
    # in the environment, e.g. API_KEYS="key1,key2".
    API_KEYS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    API_KEY_HEADER: str = "X-API-Key"

    # Rate limiting (slowapi). Empty string disables it. Format: the
    # standard "<n>/<period>" spec, e.g. "60/minute", "1000/hour".
    ENABLE_RATE_LIMIT: bool = True
    RATE_LIMIT: str = "60/minute"

    # Request caps (also act as cost guards for the paid remote APIs).
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MiB per /transcribe upload
    MAX_TEXT_CHARS: int = 5000  # per /synthesize request
    MAX_WS_SESSION_SECONDS: float = 300.0  # live-transcribe hard time cap
    MAX_WS_BYTES: int = 100 * 1024 * 1024  # live-transcribe total audio cap

    # CORS: comma-separated origins, or "*" for any. Empty disables CORS.
    CORS_ALLOW_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Secrets backend — resolve credentials from a cloud secret manager
    # at startup instead of plaintext env vars.
    # ------------------------------------------------------------------ #
    SECRETS_BACKEND: Literal["none", "aws", "azure", "gcp", "oci"] = "none"
    # Prefix/vault locator interpreted per-backend (see core/secrets.py):
    #   aws    -> Secrets Manager name prefix (e.g. "speech-bridge/")
    #   gcp    -> "projects/<id>" (Secret Manager); latest version used
    #   azure  -> Key Vault URI (e.g. "https://<vault>.vault.azure.net/")
    #   oci    -> OCI Vault OCID
    SECRETS_PREFIX: str = ""

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #
    ENABLE_METRICS: bool = True  # Prometheus /metrics endpoint
    # Set to an OTLP endpoint (e.g. "http://otel-collector:4318") to turn
    # on OpenTelemetry tracing; empty disables it.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "speech-bridge"

    # ------------------------------------------------------------------ #
    # Server
    # ------------------------------------------------------------------ #
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    # Empty string -> <system temp dir>/speech_engine
    TEMP_DIR: str = ""

    @field_validator("API_KEYS", "CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated strings for list-typed settings so they
        can be supplied via a single environment variable."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value  # let pydantic parse JSON list form
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        import os

        if os.getenv("TESTING") == "1":
            return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls))

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

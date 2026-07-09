"""Remote TTS engines: Azure Neural TTS, OpenAI TTS, Amazon Polly.

Each engine maps the canonical language codes (en/he/ar) onto the
provider's own voice catalogue (see ``core/constants.py``):

* Azure  — ``en-US-JennyNeural`` / ``he-IL-HilaNeural`` / ``ar-SA-ZariyahNeural``
* OpenAI — multilingual voices (``alloy`` by default); the model speaks
  the language of the input text.
* Polly  — ``Joanna`` (en-US) / ``Hala`` (ar-AE, neural). Polly has no
  Hebrew voice, so ``he`` raises :class:`UnsupportedLanguageError`.

SDK imports are lazy so only the enabled provider's package is needed.
"""

import asyncio
import logging
import os
from typing import Any

from speech_engine.config import get_settings
from speech_engine.core.constants import (
    AZURE_TTS_VOICES,
    POLLY_VOICES,
    require_language,
)
from speech_engine.core.exceptions import (
    ConfigurationError,
    RemoteServiceError,
    SpeechEngineError,
    UnsupportedLanguageError,
)
from speech_engine.core.tts.base import BaseTTSEngine

logger = logging.getLogger(__name__)


# =========================================================================== #
# Azure Neural TTS
# =========================================================================== #
class AzureTTSEngine(BaseTTSEngine):
    """Microsoft Azure Neural Text-to-Speech."""

    name = "azure"
    file_extension = "mp3"
    media_type = "audio/mpeg"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.AZURE_SPEECH_KEY or not settings.AZURE_SPEECH_REGION:
            raise ConfigurationError(
                "TTS_ENGINE=azure requires AZURE_SPEECH_KEY and "
                "AZURE_SPEECH_REGION to be configured."
            )
        self._settings = settings

    async def synthesize(self, text: str, language: str, output_file_path: str) -> str:
        lang = require_language(language)
        return await asyncio.to_thread(
            self._synthesize_blocking, text, lang, output_file_path
        )

    def _synthesize_blocking(self, text: str, lang: str, output_file_path: str) -> str:
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as exc:
            raise ConfigurationError(
                "TTS_ENGINE=azure requires the "
                "'azure-cognitiveservices-speech' package."
            ) from exc

        speech_config = speechsdk.SpeechConfig(
            subscription=self._settings.AZURE_SPEECH_KEY,
            region=self._settings.AZURE_SPEECH_REGION,
        )
        speech_config.speech_synthesis_voice_name = AZURE_TTS_VOICES[lang]
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioOutputConfig(filename=output_file_path),
        )
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return output_file_path
        if result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            message = getattr(details, "error_details", "") or str(
                getattr(details, "reason", "unknown")
            )
            logger.error("Azure TTS canceled: %s", message)
            raise RemoteServiceError(f"Azure TTS failed: {message}")
        raise RemoteServiceError(f"Azure TTS returned '{result.reason}'.")


# =========================================================================== #
# OpenAI TTS
# =========================================================================== #
class OpenAITTSEngine(BaseTTSEngine):
    """OpenAI TTS (multilingual voices; language follows the input text)."""

    name = "openai"
    file_extension = "mp3"
    media_type = "audio/mpeg"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise ConfigurationError(
                "TTS_ENGINE=openai requires OPENAI_API_KEY to be configured."
            )
        self._settings = settings
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise ConfigurationError(
                    "TTS_ENGINE=openai requires the 'openai' package."
                ) from exc
            self._client = AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)
        return self._client

    async def synthesize(self, text: str, language: str, output_file_path: str) -> str:
        require_language(language)  # validate even though voices are multilingual
        client = self._get_client()
        try:
            async with client.audio.speech.with_streaming_response.create(
                model=self._settings.OPENAI_TTS_MODEL,
                voice=self._settings.OPENAI_TTS_VOICE,
                input=text,
                response_format="mp3",
            ) as response:
                await response.stream_to_file(output_file_path)
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("OpenAI TTS request failed: %s", exc)
            raise RemoteServiceError(f"OpenAI TTS failed: {exc}") from exc
        return output_file_path


# =========================================================================== #
# AWS — Amazon Polly
# =========================================================================== #
class AWSTTSEngine(BaseTTSEngine):
    """Amazon Polly neural TTS (no Hebrew voice available)."""

    name = "aws"
    file_extension = "mp3"
    media_type = "audio/mpeg"

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        if settings.AWS_ACCESS_KEY_ID:
            os.environ.setdefault("AWS_ACCESS_KEY_ID", settings.AWS_ACCESS_KEY_ID)
        if settings.AWS_SECRET_ACCESS_KEY:
            os.environ.setdefault(
                "AWS_SECRET_ACCESS_KEY", settings.AWS_SECRET_ACCESS_KEY
            )
        os.environ.setdefault("AWS_DEFAULT_REGION", settings.AWS_REGION)

    async def synthesize(self, text: str, language: str, output_file_path: str) -> str:
        lang = require_language(language)
        voice = POLLY_VOICES.get(lang)
        if voice is None:
            raise UnsupportedLanguageError(
                f"Amazon Polly has no voice for '{lang}'. "
                "Use TTS_ENGINE=azure or TTS_ENGINE=local for Hebrew."
            )
        return await asyncio.to_thread(
            self._synthesize_blocking, text, voice, output_file_path
        )

    def _synthesize_blocking(
        self, text: str, voice: dict, output_file_path: str
    ) -> str:
        try:
            import boto3
        except ImportError as exc:
            raise ConfigurationError(
                "TTS_ENGINE=aws requires the 'boto3' package."
            ) from exc

        client = boto3.client("polly", region_name=self._settings.AWS_REGION)
        try:
            response = client.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=voice["voice_id"],
                Engine=voice["engine"],
                LanguageCode=voice["language_code"],
            )
            with open(output_file_path, "wb") as out:
                out.write(response["AudioStream"].read())
        except SpeechEngineError:
            raise
        except Exception as exc:
            logger.error("Amazon Polly request failed: %s", exc)
            raise RemoteServiceError(f"Amazon Polly TTS failed: {exc}") from exc
        return output_file_path

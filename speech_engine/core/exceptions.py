"""Custom exception hierarchy.

Every domain error derives from :class:`SpeechEngineError`, which carries
both an HTTP status code (used by the global FastAPI exception handler)
and a WebSocket close code (used by the live-transcription route).
"""


class SpeechEngineError(Exception):
    """Base class for all speech-engine errors."""

    status_code: int = 500
    ws_close_code: int = 1011  # Internal Error


class ConfigurationError(SpeechEngineError):
    """Missing/invalid configuration, credentials, or optional dependency."""

    status_code = 500


class UnsupportedLanguageError(SpeechEngineError):
    """A language outside of {en, he, ar} (or unsupported by the engine)."""

    status_code = 400
    ws_close_code = 4400  # application-defined: bad request


class AuthError(SpeechEngineError):
    """Missing or invalid API credentials."""

    status_code = 401
    ws_close_code = 4401  # application-defined: unauthorized


class RateLimitError(SpeechEngineError):
    """Client exceeded the configured request rate limit."""

    status_code = 429
    ws_close_code = 4429  # application-defined: too many requests


class RequestTooLargeError(SpeechEngineError):
    """Upload / streamed payload exceeded a configured size or time cap."""

    status_code = 413
    ws_close_code = 4413  # application-defined: payload too large


class AudioProcessingError(SpeechEngineError):
    """Uploaded/streamed audio could not be decoded or converted."""

    status_code = 400
    ws_close_code = 4400


class TranscriptionError(SpeechEngineError):
    """STT engine failed to produce a transcript."""

    status_code = 500


class SynthesisError(SpeechEngineError):
    """TTS engine failed to produce audio."""

    status_code = 500


class RemoteServiceError(SpeechEngineError):
    """Remote provider failure: timeout, authentication, quota, transport."""

    status_code = 502

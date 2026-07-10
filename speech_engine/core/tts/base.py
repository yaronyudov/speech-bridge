"""Abstract Base Class for TTS engines."""

from abc import ABC, abstractmethod


class BaseTTSEngine(ABC):
    """Strategy interface every TTS engine (local or remote) implements."""

    name: str = "base"
    # File extension and media type of the audio this engine produces;
    # the HTTP layer uses them to name the output file and set headers.
    file_extension: str = "mp3"
    media_type: str = "audio/mpeg"

    @abstractmethod
    async def synthesize(self, text: str, language: str, output_file_path: str) -> str:
        """Synthesize ``text`` in ``language`` into ``output_file_path``.

        Args:
            text: Plain text to speak.
            language: Canonical language code (``en``/``he``/``ar``) —
                already validated by the caller.
            output_file_path: Destination path (extension should match
                :attr:`file_extension`).

        Returns:
            The path of the generated audio file.

        Raises:
            UnsupportedLanguageError: engine has no voice for the language.
            SynthesisError / RemoteServiceError: generation failed.
        """
        raise NotImplementedError

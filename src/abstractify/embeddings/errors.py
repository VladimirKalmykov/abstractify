from __future__ import annotations


class EmbeddingValidationError(ValueError):
    """Invalid embedding input (mirrors LocalEmbeddingService ValidationError)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BackendUnavailableError(RuntimeError):
    """Model missing or inference failed (mirrors LocalEmbeddingService backend errors)."""

    code = "BACKEND_UNAVAILABLE"

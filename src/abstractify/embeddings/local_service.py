from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from abstractify.embeddings.backend import EmbeddingBackend, FastEmbedBackend
from abstractify.embeddings.errors import BackendUnavailableError, EmbeddingValidationError
from abstractify.embeddings.local_settings import LocalEmbeddingSettings

INPUT_POLICY_VERSION = 1
SUPPORTED_INPUT_TYPES = {
    "query": "query: ",
    "document": "passage: ",
}


class LocalEmbeddingService:
    """In-process embedding pipeline aligned with LocalEmbeddingService architecture."""

    def __init__(
        self,
        settings: LocalEmbeddingSettings,
        backend: EmbeddingBackend | None = None,
    ) -> None:
        self.settings = settings
        self.backend = backend or FastEmbedBackend(settings.model_id, settings.model_cache)

    def model_fingerprint(self) -> str:
        payload = {
            "provider": "fastembed",
            "runtime_version": self.backend.runtime_version,
            "model_id": self.settings.model_id,
            "dimensions": self.settings.dimensions,
            "input_policy_version": INPUT_POLICY_VERSION,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def model_loaded(self) -> bool:
        return self.backend.loaded

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "document") -> list[list[float]]:
        if input_type not in SUPPORTED_INPUT_TYPES:
            raise EmbeddingValidationError(
                "INVALID_INPUT_TYPE",
                "input_type must be query or document.",
            )
        if not texts:
            raise EmbeddingValidationError("INVALID_TEXTS", "texts must be non-empty.")
        if len(texts) > self.settings.max_batch_size:
            raise EmbeddingValidationError(
                "BATCH_TOO_LARGE",
                f"At most {self.settings.max_batch_size} texts are allowed per call.",
            )

        cleaned: list[str] = []
        total_chars = 0
        for index, value in enumerate(texts):
            if not isinstance(value, str) or not value.strip():
                raise EmbeddingValidationError(
                    "INVALID_TEXT",
                    f"texts[{index}] must be a non-empty string.",
                )
            text = value.strip()
            if len(text) > self.settings.max_text_chars:
                raise EmbeddingValidationError(
                    "TEXT_TOO_LARGE",
                    f"texts[{index}] exceeds the per-text character limit.",
                )
            total_chars += len(text)
            cleaned.append(text)

        if total_chars > self.settings.max_total_chars:
            raise EmbeddingValidationError(
                "REQUEST_TOO_LARGE",
                "The combined text size exceeds the limit.",
            )

        prefix = SUPPORTED_INPUT_TYPES[input_type]
        prepared = [prefix + text for text in cleaned]
        try:
            vectors = self.backend.embed(prepared, self.settings.batch_size)
        except BackendUnavailableError:
            raise
        except Exception as exc:
            raise BackendUnavailableError(f"Embedding inference failed: {exc}") from exc

        if len(vectors) != len(prepared):
            raise BackendUnavailableError(
                "The embedding backend returned an unexpected vector count."
            )
        for vector in vectors:
            if len(vector) != self.settings.dimensions:
                raise BackendUnavailableError(
                    "The embedding backend returned an unexpected vector dimension."
                )
        return vectors

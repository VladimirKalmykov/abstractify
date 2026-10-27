from __future__ import annotations

import threading
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol

from abstractify.embeddings.errors import BackendUnavailableError


class EmbeddingBackend(Protocol):
    @property
    def loaded(self) -> bool: ...

    @property
    def runtime_version(self) -> str: ...

    def embed(self, texts: Sequence[str], batch_size: int) -> list[list[float]]: ...


class FastEmbedBackend:
    """Lazy FastEmbed loader with thread-safe single model instance (LocalEmbeddingService pattern)."""

    def __init__(self, model_id: str, cache_dir: Path) -> None:
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def runtime_version(self) -> str:
        try:
            return version("fastembed")
        except PackageNotFoundError:
            return "unavailable"

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding
            except ImportError as error:
                raise BackendUnavailableError(
                    "FastEmbed is not installed. Use: pip install 'abstractify[local]'"
                ) from error
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._model = TextEmbedding(
                    model_name=self._model_id,
                    cache_dir=str(self._cache_dir),
                )
            except Exception as error:
                raise BackendUnavailableError(
                    f"Failed to load embedding model: {error}"
                ) from error
            return self._model

    def embed(self, texts: Sequence[str], batch_size: int) -> list[list[float]]:
        model = self._get_model()
        try:
            return [
                vector.astype("<f4", copy=False).tolist()
                for vector in model.embed(list(texts), batch_size=batch_size)
            ]
        except Exception as error:
            raise BackendUnavailableError(f"Embedding inference failed: {error}") from error

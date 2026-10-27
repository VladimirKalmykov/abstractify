from __future__ import annotations

import sys
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


def ensure_model_cached(model_id: str, cache_dir: Path, *, models: Sequence[object], download) -> None:
    """Load from the shared cache when the model is already there, otherwise download it once."""
    description = next(
        (model for model in models if str(getattr(model, "model", "")).lower() == model_id.lower()),
        None,
    )
    if description is None:
        raise BackendUnavailableError(f"Model {model_id} is not supported by FastEmbed.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = str(cache_dir)
    try:
        download(description, cache, local_files_only=True)
        return
    except (OSError, ValueError):
        print(
            f"Model {model_id} is not in {cache_dir}. Downloading it there…",
            file=sys.stderr,
            flush=True,
        )
    try:
        download(description, cache)
    except Exception as error:
        raise BackendUnavailableError(
            f"Failed to download embedding model into {cache_dir}: {error}"
        ) from error


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
                from fastembed.common.model_management import ModelManagement
            except ImportError as error:
                raise BackendUnavailableError(
                    "FastEmbed is not installed. Use: pip install 'abstractify[local]'"
                ) from error
            try:
                ensure_model_cached(
                    self._model_id,
                    self._cache_dir,
                    models=TextEmbedding._list_supported_models(),
                    download=ModelManagement.download_model,
                )
                self._model = TextEmbedding(
                    model_name=self._model_id,
                    cache_dir=str(self._cache_dir),
                    local_files_only=True,
                )
            except BackendUnavailableError:
                raise
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

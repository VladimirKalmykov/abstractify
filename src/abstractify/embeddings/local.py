from __future__ import annotations

from pathlib import Path

from abstractify.config import Config
from abstractify.embeddings.base import Embedder
from abstractify.embeddings.local_service import LocalEmbeddingService
from abstractify.embeddings.local_settings import LocalEmbeddingSettings


class LocalEmbedder(Embedder):
    """FastEmbed local vectors via LocalEmbeddingService-style pipeline."""

    name = "local"

    def __init__(
        self,
        settings: LocalEmbeddingSettings,
        service: LocalEmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self._service = service or LocalEmbeddingService(settings)
        self.name = f"fastembed:{settings.model_id}"

    def available(self) -> bool:
        try:
            import fastembed  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def loaded(self) -> bool:
        return self._service.model_loaded

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        return self._service.embed_texts(texts, input_type=input_type)


def build_local_embedder(root: Path, cfg: Config) -> LocalEmbedder:
    settings = LocalEmbeddingSettings.from_config(root, cfg)
    return LocalEmbedder(settings)


def download_model(root: Path, cfg: Config) -> None:
    """Pre-load model weights (same as first embed / init --download-model)."""
    embedder = build_local_embedder(root, cfg)
    embedder.embed(["abstractify warmup"], input_type="document")

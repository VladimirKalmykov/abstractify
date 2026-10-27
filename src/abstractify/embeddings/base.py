from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    """Create embeddings on write; retrieve is optional (cosine fallback)."""

    name: str = "base"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def retrieve(self, query: str, items: list[dict], k: int = 10) -> list[dict] | None:
        """Return ranked items or None to use default cosine over stored vectors."""
        return None

    def available(self) -> bool:
        return True

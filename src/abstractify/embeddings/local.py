from __future__ import annotations

from abstractify.embeddings.base import Embedder


class LocalEmbedder(Embedder):
    """sentence-transformers local model (~2 GB including cache). Lazy-loaded."""

    name = "local"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Local embeddings require: pip install 'abstractify[local]'"
            ) from exc
        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]


def download_model(model_name: str) -> None:
    LocalEmbedder(model_name)._load()

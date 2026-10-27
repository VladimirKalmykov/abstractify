from __future__ import annotations

import importlib.util
from pathlib import Path

from abstractify.embeddings.base import Embedder


class CustomEmbedder(Embedder):
    """Load a user adapter module: embed(texts) and optional retrieve(query, items, k)."""

    name = "custom"

    def __init__(self, adapter_path: str, project_root: Path) -> None:
        if not adapter_path:
            raise ValueError("custom_adapter path is required for custom embedding mode")
        path = Path(adapter_path)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"custom embedding adapter not found: {path}")
        spec = importlib.util.spec_from_file_location("abstractify_embed_adapter", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load adapter {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "embed"):
            raise RuntimeError("custom adapter must define embed(texts: list[str]) -> list[list[float]]")
        self._mod = mod
        self.path = path

    def embed(self, texts: list[str], *, input_type: str = "document") -> list[list[float]]:
        del input_type
        vecs = self._mod.embed(texts)
        return [[float(x) for x in v] for v in vecs]

    def retrieve(self, query: str, items: list[dict], k: int = 10) -> list[dict] | None:
        fn = getattr(self._mod, "retrieve", None)
        if fn is None:
            return None
        return fn(query, items, k)

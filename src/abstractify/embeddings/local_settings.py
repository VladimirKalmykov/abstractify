from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from abstractify.paths import project_dir
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from abstractify.config import Config

@dataclass(frozen=True)
class LocalEmbeddingSettings:
    model_id: str
    dimensions: int
    batch_size: int
    model_cache: Path
    max_batch_size: int = 64
    max_text_chars: int = 100_000
    max_total_chars: int = 250_000

    @classmethod
    def from_config(cls, root: Path, cfg: "Config") -> LocalEmbeddingSettings:
        from abstractify.config import (
            DEFAULT_EMBED_BATCH_SIZE,
            DEFAULT_EMBED_DIMENSIONS,
            DEFAULT_LOCAL_MODEL,
        )

        cache_env = os.environ.get("ABSTRACTIFY_EMBED_MODEL_CACHE", "").strip()
        cache = Path(cache_env) if cache_env else project_dir(root) / "models"
        batch_env = os.environ.get("ABSTRACTIFY_EMBED_BATCH_SIZE", "").strip()
        batch_size = int(batch_env) if batch_env else getattr(
            cfg, "embed_batch_size", DEFAULT_EMBED_BATCH_SIZE
        )
        dim_env = os.environ.get("ABSTRACTIFY_EMBED_DIMENSIONS", "").strip()
        dimensions = int(dim_env) if dim_env else getattr(
            cfg, "embed_dimensions", DEFAULT_EMBED_DIMENSIONS
        )
        model_env = os.environ.get("ABSTRACTIFY_EMBED_MODEL", "").strip()
        model_id = model_env or getattr(cfg, "embed_model", DEFAULT_LOCAL_MODEL)
        return cls(
            model_id=model_id,
            dimensions=dimensions,
            batch_size=batch_size,
            model_cache=cache,
        )

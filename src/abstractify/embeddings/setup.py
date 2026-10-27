from __future__ import annotations

from pathlib import Path

from abstractify.config import (
    DEFAULT_EMBED_DIMENSIONS,
    DEFAULT_LOCAL_MODEL,
    Config,
    load_config,
    save_config,
)

# LocalEmbeddingService default (127.0.0.1:7342, POST /v1/embeddings)
DEFAULT_LES_EMBED_URL = "http://127.0.0.1:7342/v1/embeddings"


def configure_embeddings(
    root: Path,
    *,
    mode: str,
    embed_url: str | None = None,
) -> Config:
    """Turn on local or REST embeddings without re-running init (graphs unchanged)."""
    if mode not in ("local", "rest"):
        raise ValueError("configure_embeddings supports embed_mode local or rest only")
    cfg = load_config(root.resolve())
    cfg.embed_mode = mode
    cfg.embed_model = DEFAULT_LOCAL_MODEL
    cfg.embed_dimensions = DEFAULT_EMBED_DIMENSIONS
    if mode == "rest":
        cfg.embed_url = (embed_url or DEFAULT_LES_EMBED_URL).strip()
        if not cfg.embed_url:
            raise ValueError("embed_url is required for rest mode")
    else:
        cfg.embed_url = ""
    save_config(root, cfg)
    return cfg

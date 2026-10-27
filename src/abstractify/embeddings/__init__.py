from __future__ import annotations

from pathlib import Path

from abstractify.embeddings.base import Embedder


def build_embedder(cfg, project_root: Path) -> Embedder:
    from abstractify.config import Config

    if not isinstance(cfg, Config):
        raise TypeError("cfg must be a Config instance")
    mode = cfg.embed_mode
    if mode == "none":
        from abstractify.embeddings.none import NoneEmbedder

        return NoneEmbedder()
    if mode == "local":
        from abstractify.embeddings.local import build_local_embedder

        return build_local_embedder(project_root, cfg)
    if mode == "rest":
        from abstractify.embeddings.rest import RestEmbedder

        return RestEmbedder(cfg.embed_url, api_key=cfg.embed_api_key())
    if mode == "custom":
        from abstractify.embeddings.custom import CustomEmbedder

        return CustomEmbedder(cfg.custom_adapter, project_root)
    raise ValueError(f"unknown embed_mode {mode!r}")

from __future__ import annotations

from pathlib import Path

from abstractify.config import Config
from abstractify.embeddings.base import Embedder
from abstractify.embeddings.custom import CustomEmbedder
from abstractify.embeddings.local import LocalEmbedder
from abstractify.embeddings.none import NoneEmbedder
from abstractify.embeddings.rest import RestEmbedder


def build_embedder(cfg: Config, project_root: Path) -> Embedder:
    mode = cfg.embed_mode
    if mode == "none":
        return NoneEmbedder()
    if mode == "local":
        return LocalEmbedder(cfg.embed_model)
    if mode == "rest":
        return RestEmbedder(cfg.embed_url, api_key=cfg.embed_api_key())
    if mode == "custom":
        return CustomEmbedder(cfg.custom_adapter, project_root)
    raise ValueError(f"unknown embed_mode {mode!r}")

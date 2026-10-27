from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import tomllib

from abstractify.paths import config_path, project_dir

EMBED_MODES = ("local", "rest", "none", "custom")
KNOWN_RELATIONS = ("knows_about", "does_not_know_about", "calls", "responds_to")
GRAPH_KINDS = ("structural", "flow")

DEFAULT_LOCAL_MODEL = "BAAI/bge-large-en-v1.5"


@dataclass
class Config:
    embed_mode: str = "none"
    embed_url: str = ""
    embed_model: str = DEFAULT_LOCAL_MODEL
    custom_adapter: str = ""
    max_entities_per_graph: int = 80
    max_edges_per_graph: int = 200
    hard_max_entities: int = 500
    ui_port: int = 8765
    mcp_port: int = 8766
    ui_host: str = "127.0.0.1"

    def embed_api_key(self) -> str:
        return os.environ.get("ABSTRACTIFY_EMBED_API_KEY", "")


def _toml_dumps(cfg: Config) -> str:
    data = asdict(cfg)
    lines = [
        "# Abstractify project config. API keys belong in ABSTRACTIFY_EMBED_API_KEY.",
        f'embed_mode = "{data["embed_mode"]}"',
        f'embed_url = "{data["embed_url"]}"',
        f'embed_model = "{data["embed_model"]}"',
        f'custom_adapter = "{data["custom_adapter"]}"',
        f'max_entities_per_graph = {data["max_entities_per_graph"]}',
        f'max_edges_per_graph = {data["max_edges_per_graph"]}',
        f'hard_max_entities = {data["hard_max_entities"]}',
        f'ui_port = {data["ui_port"]}',
        f'mcp_port = {data["mcp_port"]}',
        f'ui_host = "{data["ui_host"]}"',
        "",
    ]
    return "\n".join(lines)


def save_config(root: Path, cfg: Config) -> None:
    project_dir(root).mkdir(parents=True, exist_ok=True)
    config_path(root).write_text(_toml_dumps(cfg), encoding="utf-8")


def load_config(root: Path) -> Config:
    raw = tomllib.loads(config_path(root).read_text(encoding="utf-8"))
    cfg = Config()
    for key in asdict(cfg):
        if key in raw:
            setattr(cfg, key, raw[key])
    if cfg.embed_mode not in EMBED_MODES:
        raise ValueError(f"unknown embed_mode {cfg.embed_mode!r}; expected {EMBED_MODES}")
    return cfg

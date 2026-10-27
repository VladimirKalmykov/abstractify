from __future__ import annotations

import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

import tomllib

from abstractify.paths import config_path, project_dir

EMBED_MODES = ("local", "rest", "none", "custom")
KNOWN_RELATIONS = ("knows_about", "does_not_know_about", "calls", "responds_to")
GRAPH_KINDS = ("structural", "flow")

DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_EMBED_DIMENSIONS = 1024
DEFAULT_EMBED_BATCH_SIZE = 16


@dataclass
class Config:
    embed_mode: str = "none"
    embed_url: str = ""
    embed_model: str = DEFAULT_LOCAL_MODEL
    embed_dimensions: int = DEFAULT_EMBED_DIMENSIONS
    embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE
    custom_adapter: str = ""
    max_entities_per_graph: int = 80
    max_edges_per_graph: int = 200
    hard_max_entities: int = 500
    ui_port: int = 8765
    mcp_port: int = 8766
    ui_host: str = "127.0.0.1"

    def embed_api_key(self) -> str:
        return os.environ.get("ABSTRACTIFY_EMBED_API_KEY", "")


def _try_bind(host: str, port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock


def allocate_localhost_ports(
    host: str = "127.0.0.1",
    *,
    preferred_mcp: int = 8766,
    preferred_ui: int = 8765,
) -> tuple[int, int]:
    """Return free (mcp_port, ui_port) on localhost, preferring the usual defaults."""
    sockets: list[socket.socket] = []
    try:
        mcp_sock = _try_bind(host, preferred_mcp) if preferred_mcp else None
        if mcp_sock is None:
            mcp_sock = _try_bind(host, 0)
        if mcp_sock is None:
            raise OSError(f"no free TCP port on {host} for MCP")
        sockets.append(mcp_sock)

        ui_sock = _try_bind(host, preferred_ui) if preferred_ui else None
        if ui_sock is None:
            ui_sock = _try_bind(host, 0)
        if ui_sock is None:
            raise OSError(f"no free TCP port on {host} for UI")
        sockets.append(ui_sock)

        mcp_port = int(mcp_sock.getsockname()[1])
        ui_port = int(ui_sock.getsockname()[1])
        if mcp_port == ui_port:
            extra = _try_bind(host, 0)
            if extra is None:
                raise OSError(f"no free TCP port on {host} for UI")
            sockets.append(extra)
            ui_port = int(extra.getsockname()[1])
        return mcp_port, ui_port
    finally:
        for sock in sockets:
            sock.close()


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_dumps(cfg: Config) -> str:
    data = asdict(cfg)
    lines = [
        "# Abstractify project config. API keys belong in ABSTRACTIFY_EMBED_API_KEY.",
        f'embed_mode = "{_toml_escape(data["embed_mode"])}"',
        f'embed_url = "{_toml_escape(data["embed_url"])}"',
        f'embed_model = "{_toml_escape(data["embed_model"])}"',
        f"embed_dimensions = {data['embed_dimensions']}",
        f"embed_batch_size = {data['embed_batch_size']}",
        f'custom_adapter = "{_toml_escape(data["custom_adapter"])}"',
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

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from abstractify.cli import main
from abstractify.config import allocate_localhost_ports, load_config, save_config
from abstractify.embeddings import build_embedder
from abstractify.mcp_server import build_server
from abstractify.project import SKILL_MARKER_BEGIN, SKILL_MARKER_END, init_project
from abstractify.size import GraphTooLarge
from abstractify.store import Store, open_store


def _init(tmp: Path, **kwargs) -> Path:
    kwargs.setdefault("example", False)
    init_project(tmp, embed_mode="none", **kwargs)
    return tmp


def test_init_creates_sqlite_and_skill(tmp_path: Path) -> None:
    _init(tmp_path)
    assert (tmp_path / ".abstractify" / "config.toml").is_file()
    assert (tmp_path / ".abstractify" / "abstractify.db").is_file()
    assert (tmp_path / ".cursor" / "skills" / "abstractify" / "SKILL.md").is_file()
    assert (tmp_path / "AGENTS.md").is_file()
    cfg = load_config(tmp_path)
    assert cfg.embed_mode == "none"
    assert cfg.ui_port > 0
    assert cfg.mcp_port > 0
    assert cfg.ui_port != cfg.mcp_port
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- abstractify:begin -->" in agents
    assert "Do **not** run `abstractify init` yourself" in agents
    assert "you may run `abstractify start` yourself" in agents
    assert f"`127.0.0.1:{cfg.mcp_port}`" in agents
    assert f"http://127.0.0.1:{cfg.ui_port}" in agents


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, _format: str, *args: object) -> None:
        return


class _SilentServer(HTTPServer):
    allow_reuse_address = True


def _listen(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    return sock


def _http_up(host: str, port: int) -> HTTPServer:
    httpd = _SilentServer((host, port), _OkHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def test_allocate_localhost_ports_skips_busy() -> None:
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    port = int(busy.getsockname()[1])
    try:
        mcp, ui = allocate_localhost_ports(preferred_mcp=port, preferred_ui=port)
        assert mcp != port
        assert ui != port
        assert mcp != ui
    finally:
        busy.close()


def test_init_writes_ports_to_config_and_agents_md(tmp_path: Path) -> None:
    init_project(tmp_path)
    cfg = load_config(tmp_path)
    raw = (tmp_path / ".abstractify" / "config.toml").read_text(encoding="utf-8")
    assert f"mcp_port = {cfg.mcp_port}" in raw
    assert f"ui_port = {cfg.ui_port}" in raw
    assert f'ui_host = "{cfg.ui_host}"' in raw
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    begin = text.index(SKILL_MARKER_BEGIN)
    end = text.index(SKILL_MARKER_END)
    block = text[begin:end]
    assert f"{cfg.ui_host}:{cfg.mcp_port}" in block
    assert f"http://{cfg.ui_host}:{cfg.ui_port}" in block
    assert SKILL_MARKER_END in text


def test_init_projects_can_get_different_ports(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    init_project(first)
    cfg_a = load_config(first)
    holders = [
        _listen(cfg_a.ui_host, cfg_a.mcp_port),
        _listen(cfg_a.ui_host, cfg_a.ui_port),
    ]
    try:
        init_project(second)
        cfg_b = load_config(second)
        assert {cfg_b.mcp_port, cfg_b.ui_port}.isdisjoint({cfg_a.mcp_port, cfg_a.ui_port})
        text = (second / "AGENTS.md").read_text(encoding="utf-8")
        begin = text.index(SKILL_MARKER_BEGIN)
        end = text.index(SKILL_MARKER_END)
        block = text[begin:end]
        assert f"{cfg_b.ui_host}:{cfg_b.mcp_port}" in block
        assert f"http://{cfg_b.ui_host}:{cfg_b.ui_port}" in block
    finally:
        for sock in holders:
            sock.close()


def test_status_probes_configured_ports(tmp_path: Path) -> None:
    init_project(tmp_path)
    cfg = load_config(tmp_path)
    mcp, ui = allocate_localhost_ports(preferred_mcp=0, preferred_ui=0)
    cfg.mcp_port = mcp
    cfg.ui_port = ui
    save_config(tmp_path, cfg)
    assert main(["status", str(tmp_path)]) == 1
    servers = [_http_up(cfg.ui_host, mcp), _http_up(cfg.ui_host, ui)]
    try:
        assert main(["status", str(tmp_path)]) == 0
    finally:
        for httpd in servers:
            httpd.shutdown()
            httpd.server_close()


def test_graph_create_update_json_export(tmp_path: Path) -> None:
    _init(tmp_path)
    store = open_store(tmp_path)
    g = store.create_graph(
        name="Languages",
        kind="structural",
        principle="Split the project by programming language.",
        entities=[
            {
                "name": "Python package",
                "description": "CLI and SQLite backend.",
                "code_refs": [{"path": "abstractify/src/abstractify/cli.py", "start_line": 1, "end_line": 40}],
            },
            {
                "name": "React UI",
                "description": "Localhost graph viewer.",
                "code_refs": [{"path": "abstractify/src/abstractify/ui/src/App.tsx"}],
            },
        ],
        edges=[{"source": "Python package", "target": "React UI", "relation": "calls"}],
    )
    assert g["principle"].startswith("Split the project")
    assert len(g["entities"]) == 2
    assert g["edges"][0]["relation"] == "calls"
    json_path = tmp_path / ".abstractify" / "graphs" / f"{g['id']}.json"
    assert json_path.is_file()
    dumped = json.loads(json_path.read_text())
    assert dumped["source_of_truth"] == "sqlite"

    updated = store.update_graph(g["id"], description="updated slice")
    assert updated["description"] == "updated slice"
    store.close()


def test_targeted_edits_meta_links_reverse_index(tmp_path: Path) -> None:
    _init(tmp_path)
    store = open_store(tmp_path)
    g = store.create_graph(
        name="Net",
        kind="flow",
        principle="Group by request flow.",
        entities=[{"name": "Gateway", "description": "front door"}],
    )
    store.upsert_entity(
        {
            "name": "Worker",
            "description": "handles jobs",
            "code_refs": [{"path": "src/worker.py", "start_line": 10, "end_line": 40}],
        },
        graph_id=g["id"],
    )
    store.upsert_edge(g["id"], {"source": "Gateway", "target": "Worker", "relation": "responds_to"})
    store.add_meta_link("Gateway", "Worker", "paired_with", "same slice")
    hits = store.lookup_by_file("src/worker.py", start_line=12, end_line=12)
    assert [h["name"] for h in hits] == ["Worker"]
    affected = store.affected_by_files(["src/worker.py"])
    assert affected["entities"][0]["name"] == "Worker"
    assert affected["graphs"][0]["name"] == "Net"
    assert "does not auto-mutate" in affected["note"]
    path = store.shortest_path("Gateway", "Worker")
    assert path["found"] is True
    explained = store.explain("Gateway")
    assert explained["entity"]["name"] == "Gateway"
    store.close()


def test_search_idf_and_snapshot(tmp_path: Path) -> None:
    _init(tmp_path, example=True)
    store = open_store(tmp_path)
    res = store.search("auth credentials")
    names = [h["name"] for h in res["hits"]]
    assert "Auth Service" in names
    graphs = store.list_graphs()
    snap = store.create_snapshot(graphs[0]["id"], label="v1")
    assert (tmp_path / ".abstractify" / "snapshots" / f"{snap['id']}.json").is_file()
    store.update_graph(graphs[0]["id"], name="Renamed")
    restored = store.restore_snapshot(snap["id"])
    assert restored["name"] == "Core services"
    store.close()


def test_size_protection(tmp_path: Path) -> None:
    _init(tmp_path)
    cfg = load_config(tmp_path)
    cfg.max_entities_per_graph = 2
    cfg.max_edges_per_graph = 10
    save_config(tmp_path, cfg)
    store = open_store(tmp_path)
    with pytest.raises(GraphTooLarge):
        store.create_graph(
            name="Huge",
            kind="structural",
            principle="too many",
            entities=[
                {"name": "A", "description": "a"},
                {"name": "B", "description": "b"},
                {"name": "C", "description": "c"},
            ],
        )
    store.create_graph(
        name="Huge",
        kind="structural",
        principle="too many",
        entities=[
            {"name": "A", "description": "a"},
            {"name": "B", "description": "b"},
            {"name": "C", "description": "c"},
        ],
        confirm_large=True,
    )
    store.close()


def test_custom_embedder(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "def embed(texts):\n"
        "    return [[float(len(t)), 1.0] for t in texts]\n",
        encoding="utf-8",
    )
    init_project(tmp_path, embed_mode="custom", custom_adapter=str(adapter))
    store = open_store(tmp_path)
    store.upsert_entity({"name": "Alpha", "description": "first concept here"})
    store.upsert_entity({"name": "Beta", "description": "second idea"})
    res = store.search("first concept")
    assert res["hits"]
    store.close()


def test_cli_graph_flow(tmp_path: Path) -> None:
    assert main(["init", str(tmp_path), "--embed-mode", "none", "--example"]) == 0
    assert main(["graph", "list", "--path", str(tmp_path)]) == 0
    assert main(["search", "gateway", "--path", str(tmp_path)]) == 0
    assert main(["affected", "src/gateway.py", "--path", str(tmp_path)]) == 0


def test_mcp_tools_registered(tmp_path: Path) -> None:
    import asyncio

    _init(tmp_path)
    store = open_store(tmp_path)
    server = build_server(store)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    store.close()
    for expected in (
        "create_graph",
        "update_graph",
        "delete_graph",
        "upsert_edge",
        "upsert_entity",
        "add_meta_link",
        "lookup_by_file",
        "search",
        "path",
        "explain",
        "create_snapshot",
        "affected_by_files",
        "restore_snapshot",
    ):
        assert expected in names, expected


def test_sqlite_is_source_of_truth(tmp_path: Path) -> None:
    _init(tmp_path, example=True)
    store = open_store(tmp_path)
    g = store.list_graphs()[0]
    json_file = tmp_path / ".abstractify" / "graphs" / f"{g['id']}.json"
    json_file.write_text('{"schema_version":1,"id":"tampered","entities":[]}\n', encoding="utf-8")
    again = store.get_graph(g["id"])
    assert again is not None
    assert again["name"] == "Core services"
    assert len(again["entities"]) == 3
    store.close()

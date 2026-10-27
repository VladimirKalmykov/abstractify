from __future__ import annotations

import json
import shutil
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


def test_version_command_prints_only_the_number(capsys: pytest.CaptureFixture[str]) -> None:
    from abstractify import __version__

    assert main(["version"]) == 0
    assert capsys.readouterr().out == f"{__version__}\n"
    assert main(["v"]) == 0
    assert capsys.readouterr().out == f"{__version__}\n"


def _init(tmp: Path, **kwargs) -> Path:
    kwargs.setdefault("example", False)
    init_project(tmp, embed_mode="none", **kwargs)
    return tmp


def test_init_creates_sqlite_and_skill(tmp_path: Path) -> None:
    _init(tmp_path)
    assert (tmp_path / ".abstractify" / "config.toml").is_file()
    assert (tmp_path / ".abstractify" / "abstractify.db").is_file()
    assert (tmp_path / ".cursor" / "skills" / "abstractify" / "SKILL.md").is_file()
    mcp = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["abstractify"] == {
        "command": "abstractify",
        "args": ["serve", tmp_path.resolve().as_posix()],
    }
    assert not (tmp_path / ".parser").exists()
    assert not (tmp_path / "parsers").exists()
    agents_skill = (tmp_path / ".agents" / "skills" / "abstractify" / "SKILL.md").read_text(encoding="utf-8")
    assert "After every task that changes files, look up the linked abstractions and correct them." in agents_skill
    assert (tmp_path / "AGENTS.md").is_file()
    cfg = load_config(tmp_path)
    assert cfg.embed_mode == "none"
    assert cfg.ui_port > 0
    assert cfg.mcp_port > 0
    assert cfg.ui_port != cfg.mcp_port
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- abstractify:begin -->" in agents
    assert "Do **not** run `abstractify init` yourself" in agents
    assert "Always work with Abstractify." in agents
    assert "you **must** run `abstractify start` yourself" in agents
    assert "You **must not** bypass it by writing directly to the database" in agents
    assert "Direct editing of the database is completely forbidden" in agents
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


def test_init_only_agents_requires_existing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["init", "--only-agents", str(tmp_path)])
    assert code == 1
    err = capsys.readouterr().err
    assert "not initialized" in err
    assert "no agent instruction" in err
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".abstractify").exists()
    assert not (tmp_path / ".cursor").exists()


def test_init_only_skill_installs_skills_without_touching_project(tmp_path: Path) -> None:
    init_project(tmp_path, example=True)
    config_file = tmp_path / ".abstractify" / "config.toml"
    db_file = tmp_path / ".abstractify" / "abstractify.db"
    agents = tmp_path / "AGENTS.md"
    config_before = config_file.read_text(encoding="utf-8")
    db_before = db_file.read_bytes()
    agents_before = agents.read_text(encoding="utf-8")
    mcp_file = tmp_path / ".cursor" / "mcp.json"
    mcp_before = json.loads(mcp_file.read_text(encoding="utf-8"))
    mcp_before["mcpServers"]["other"] = {"command": "other"}
    mcp_file.write_text(json.dumps(mcp_before), encoding="utf-8")
    mcp_before_text = mcp_file.read_text(encoding="utf-8")
    agents_skill = tmp_path / ".agents" / "skills" / "abstractify" / "SKILL.md"
    agents_skill.write_text("stale skill\n", encoding="utf-8")
    assert main(["init", "--only-skill", str(tmp_path)]) == 0
    assert config_file.read_text(encoding="utf-8") == config_before
    assert db_file.read_bytes() == db_before
    assert agents.read_text(encoding="utf-8") == agents_before
    assert mcp_file.read_text(encoding="utf-8") == mcp_before_text
    text = agents_skill.read_text(encoding="utf-8")
    assert "stale skill" not in text
    assert "Direct editing of the database is completely forbidden." in text
    assert "ask the user for permission first" in text
    assert (tmp_path / ".cursor" / "skills" / "abstractify" / "SKILL.md").is_file()
    assert not (tmp_path / ".parser").exists()
    assert not (tmp_path / "parsers").exists()


def test_init_mirrors_agents_skill_into_parser_skills_when_parsers_exists(tmp_path: Path) -> None:
    parsers = tmp_path / "parsers"
    parsers.mkdir()
    marker = parsers / "kept.txt"
    marker.write_text("keep\n", encoding="utf-8")
    init_project(tmp_path)
    agents_skill = tmp_path / ".agents" / "skills" / "abstractify" / "SKILL.md"
    parser_skill = tmp_path / ".parser" / "skills" / "abstractify" / "SKILL.md"
    assert parser_skill.is_file()
    assert parser_skill.read_text(encoding="utf-8") == agents_skill.read_text(encoding="utf-8")
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert list(parsers.iterdir()) == [marker]


def test_only_skill_mirrors_agents_skill_when_parsers_exists(tmp_path: Path) -> None:
    init_project(tmp_path)
    parsers = tmp_path / "parsers"
    parsers.mkdir()
    agents_skill = tmp_path / ".agents" / "skills" / "abstractify" / "SKILL.md"
    parser_skill = tmp_path / ".parser" / "skills" / "abstractify" / "SKILL.md"
    parser_skill.parent.mkdir(parents=True)
    parser_skill.write_text("stale parser skill\n", encoding="utf-8")
    agents_skill.write_text("stale agents skill\n", encoding="utf-8")
    assert main(["init", "--only-skill", str(tmp_path)]) == 0
    text = agents_skill.read_text(encoding="utf-8")
    assert text == parser_skill.read_text(encoding="utf-8")
    assert "stale" not in text
    assert "Direct editing of the database is completely forbidden." in text
    assert list(parsers.iterdir()) == []


def test_init_only_mcp_writes_server_and_keeps_other_entries(tmp_path: Path) -> None:
    init_project(tmp_path)
    config_file = tmp_path / ".abstractify" / "config.toml"
    db_file = tmp_path / ".abstractify" / "abstractify.db"
    agents = tmp_path / "AGENTS.md"
    skill = tmp_path / ".cursor" / "skills" / "abstractify" / "SKILL.md"
    config_before = config_file.read_text(encoding="utf-8")
    db_before = db_file.read_bytes()
    agents_before = agents.read_text(encoding="utf-8")
    skill_before = skill.read_text(encoding="utf-8")
    mcp_file = tmp_path / ".cursor" / "mcp.json"
    mcp_file.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"url": "http://127.0.0.1:9/mcp"},
                    "abstractify": {"command": "stale", "args": ["serve", "/stale"]},
                }
            }
        ),
        encoding="utf-8",
    )
    assert main(["init", "--only-mcp", str(tmp_path)]) == 0
    assert config_file.read_text(encoding="utf-8") == config_before
    assert db_file.read_bytes() == db_before
    assert agents.read_text(encoding="utf-8") == agents_before
    assert skill.read_text(encoding="utf-8") == skill_before
    saved = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["other"] == {"url": "http://127.0.0.1:9/mcp"}
    assert saved["mcpServers"]["abstractify"] == {
        "command": "abstractify",
        "args": ["serve", tmp_path.resolve().as_posix()],
    }


def test_init_only_mcp_creates_file_without_other_install_steps(tmp_path: Path) -> None:
    init_project(tmp_path)
    agents_skill = tmp_path / ".agents" / "skills" / "abstractify" / "SKILL.md"
    agents_before = agents_skill.read_text(encoding="utf-8")
    cursor = tmp_path / ".cursor"
    shutil.rmtree(cursor)
    assert main(["init", "--only-mcp", str(tmp_path)]) == 0
    saved = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
    assert saved["mcpServers"]["abstractify"]["args"] == ["serve", tmp_path.resolve().as_posix()]
    assert not (cursor / "skills").exists()
    assert agents_skill.read_text(encoding="utf-8") == agents_before


def test_init_merges_existing_mcp_json(tmp_path: Path) -> None:
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text(
        json.dumps(
            {
                "extra": True,
                "mcpServers": {"other": {"command": "keep-me"}},
            }
        ),
        encoding="utf-8",
    )
    init_project(tmp_path)
    saved = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
    assert saved["extra"] is True
    assert saved["mcpServers"]["other"] == {"command": "keep-me"}
    assert saved["mcpServers"]["abstractify"] == {
        "command": "abstractify",
        "args": ["serve", tmp_path.resolve().as_posix()],
    }


def test_init_only_mcp_requires_existing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["init", "--only-mcp", str(tmp_path)])
    assert code == 1
    err = capsys.readouterr().err
    assert "not initialized" in err
    assert "no project to configure MCP" in err
    assert not (tmp_path / ".cursor").exists()
    assert not (tmp_path / ".abstractify").exists()


def test_init_only_skill_requires_existing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["init", "--only-skill", str(tmp_path)])
    assert code == 1
    assert "not initialized" in capsys.readouterr().err
    assert not (tmp_path / ".agents").exists()


def test_init_only_agents_rewrites_agents_block_only(tmp_path: Path) -> None:
    init_project(tmp_path, example=True)
    config_file = tmp_path / ".abstractify" / "config.toml"
    db_file = tmp_path / ".abstractify" / "abstractify.db"
    config_before = config_file.read_text(encoding="utf-8")
    db_before = db_file.read_bytes()
    skill = tmp_path / ".cursor" / "skills" / "abstractify" / "SKILL.md"
    skill.write_text("custom skill\n", encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "keep me\n\n<!-- abstractify:begin -->\nstale\n<!-- abstractify:end -->\n\ntrailer\n",
        encoding="utf-8",
    )
    assert main(["init", "--only-agents", str(tmp_path)]) == 0
    assert config_file.read_text(encoding="utf-8") == config_before
    assert db_file.read_bytes() == db_before
    assert skill.read_text(encoding="utf-8") == "custom skill\n"
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("keep me\n")
    assert text.rstrip().endswith("trailer")
    assert "stale" not in text
    assert "Do **not** run `abstractify init` yourself" in text
    cfg = load_config(tmp_path)
    assert f"`127.0.0.1:{cfg.mcp_port}`" in text


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


def test_backfill_after_enabling_custom_embedder(tmp_path: Path) -> None:
    assert main(["init", str(tmp_path), "--embed-mode", "none", "--example"]) == 0
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "def embed(texts, input_type='document'):\n"
        "    del input_type\n"
        "    return [[1.0, 0.0] * 512 for _ in texts]\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    cfg.embed_mode = "custom"
    cfg.custom_adapter = str(adapter)
    cfg.embed_dimensions = 1024
    save_config(tmp_path, cfg)
    store = open_store(tmp_path, backfill_embeddings=False)
    try:
        report = store.backfill_missing_embeddings()
        assert report["embedded"] >= 3
        row = store._conn.execute("SELECT COUNT(*) FROM entity_embeddings").fetchone()[0]
        assert row >= 3
    finally:
        store.close()


def test_configure_embeddings_rest_without_init(tmp_path: Path) -> None:
    from abstractify.embeddings.setup import DEFAULT_LES_EMBED_URL, configure_embeddings

    init_project(tmp_path, embed_mode="none", example=True)
    cfg = configure_embeddings(tmp_path, mode="rest")
    assert cfg.embed_mode == "rest"
    assert cfg.embed_url == DEFAULT_LES_EMBED_URL
    assert cfg.embed_dimensions == 1024


def test_local_embedding_service_uses_input_prefixes() -> None:
    from abstractify.embeddings.backend import EmbeddingBackend
    from abstractify.embeddings.local_service import LocalEmbeddingService
    from abstractify.embeddings.local_settings import LocalEmbeddingSettings

    seen: list[str] = []

    class MockBackend:
        loaded = False
        runtime_version = "test"

        def embed(self, texts, batch_size):
            seen.extend(texts)
            return [[0.0] * 1024 for _ in texts]

    settings = LocalEmbeddingSettings(
        model_id="test-model",
        dimensions=1024,
        batch_size=8,
        model_cache=Path("/tmp/unused"),
    )
    svc = LocalEmbeddingService(settings, backend=MockBackend())  # type: ignore[arg-type]
    svc.embed_texts(["hello"], input_type="document")
    svc.embed_texts(["world"], input_type="query")
    assert seen == ["passage: hello", "query: world"]


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


def test_entity_metadata_migrates_existing_v1_database(tmp_path: Path) -> None:
    import sqlite3

    from abstractify.config import Config, save_config
    from abstractify.paths import db_path

    save_config(tmp_path, Config(embed_mode="none"))
    db = db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '1');
        CREATE TABLE entities (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO entities(id, name, description, created_at, updated_at)
        VALUES ('e_old', 'Old', 'kept', 't', 't');
        """
    )
    conn.commit()
    conn.close()

    store = open_store(tmp_path, backfill_embeddings=False)
    version = store._conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    assert version["value"] == "4"
    columns = [info["name"] for info in store._conn.execute("PRAGMA table_info(entities)")]
    assert "metadata" in columns
    kept = store._conn.execute(
        "SELECT name, description, metadata FROM entities WHERE id = 'e_old'"
    ).fetchone()
    assert kept["name"] == "Old"
    assert kept["description"] == "kept"
    assert kept["metadata"] == "{}"
    store.close()


def test_code_ref_line_states(tmp_path: Path) -> None:
    _init(tmp_path)
    store = open_store(tmp_path, backfill_embeddings=False)
    ent = store.upsert_entity(
        {
            "name": "Bound",
            "code_refs": [
                {"path": "src/whole.py"},
                {"path": "src/one.py", "start_line": 12},
                {"path": "src/range.py", "start_line": 4, "end_line": 9},
            ],
        }
    )
    by_path = {ref["path"]: ref for ref in ent["code_refs"]}
    assert by_path["src/whole.py"]["start_line"] is None
    assert by_path["src/whole.py"]["end_line"] is None
    assert by_path["src/one.py"]["start_line"] == 12
    assert by_path["src/one.py"]["end_line"] is None
    assert by_path["src/range.py"]["start_line"] == 4
    assert by_path["src/range.py"]["end_line"] == 9

    with pytest.raises(ValueError, match="start_line is required when end_line is set"):
        store.upsert_entity(
            {"name": "Bound", "code_refs": [{"path": "src/bad.py", "end_line": 3}]}
        )
    with pytest.raises(ValueError, match="cannot be less than start_line"):
        store.upsert_entity(
            {
                "name": "Bound",
                "code_refs": [{"path": "src/bad.py", "start_line": 8, "end_line": 2}],
            }
        )
    kept = {ref["path"] for ref in store.get_entity("Bound")["code_refs"]}
    assert kept == {"src/whole.py", "src/one.py", "src/range.py"}
    store.close()

    assert (
        main(
            [
                "entity",
                "upsert",
                "--name",
                "FromCli",
                "--code-ref",
                "src/whole.py",
                "--code-ref",
                "src/one.py:12",
                "--code-ref",
                "src/range.py:4:9",
                "--path",
                str(tmp_path),
            ]
        )
        == 0
    )
    store = open_store(tmp_path, backfill_embeddings=False)
    by_path = {ref["path"]: ref for ref in store.get_entity("FromCli")["code_refs"]}
    assert by_path["src/whole.py"]["start_line"] is None and by_path["src/whole.py"]["end_line"] is None
    assert by_path["src/one.py"]["start_line"] == 12 and by_path["src/one.py"]["end_line"] is None
    assert by_path["src/range.py"]["start_line"] == 4 and by_path["src/range.py"]["end_line"] == 9
    store.close()
    assert (
        main(
            ["entity", "upsert", "--name", "FromCli", "--code-ref", "src/bad.py:9:2", "--path", str(tmp_path)]
        )
        == 1
    )
    assert (
        main(
            ["entity", "upsert", "--name", "FromCli", "--code-ref", "src/bad.py::4", "--path", str(tmp_path)]
        )
        == 1
    )


def test_code_ref_lines_migrate_existing_v2_database(tmp_path: Path) -> None:
    import sqlite3

    from abstractify.config import Config, save_config
    from abstractify.paths import db_path

    save_config(tmp_path, Config(embed_mode="none"))
    db = db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '2');
        CREATE TABLE entities (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          metadata TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        INSERT INTO entities(id, name, description, metadata, created_at, updated_at)
        VALUES ('e_old', 'Old', 'kept', '{}', 't', 't');
        CREATE TABLE code_refs (
          id TEXT PRIMARY KEY,
          entity_id TEXT NOT NULL,
          path TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO code_refs(id, entity_id, path, note)
        VALUES ('c_old', 'e_old', 'src/mod.ts', 'module');
        """
    )
    conn.commit()
    conn.close()

    store = open_store(tmp_path, backfill_embeddings=False)
    version = store._conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    assert version["value"] == "4"
    columns = [info["name"] for info in store._conn.execute("PRAGMA table_info(code_refs)")]
    assert "start_line" in columns
    assert "end_line" in columns
    kept = store._conn.execute(
        "SELECT path, note, start_line, end_line FROM code_refs WHERE id = 'c_old'"
    ).fetchone()
    assert kept["path"] == "src/mod.ts"
    assert kept["note"] == "module"
    assert kept["start_line"] is None
    assert kept["end_line"] is None
    meta_col = next(
        info
        for info in store._conn.execute("PRAGMA table_info(entities)")
        if info["name"] == "metadata"
    )
    assert str(meta_col["type"]).upper() == "JSON"
    old = store.get_entity("e_old")
    assert old is not None
    assert old["metadata"] == {}
    store.close()


def test_entity_metadata_json_roundtrip(tmp_path: Path) -> None:
    _init(tmp_path)
    store = open_store(tmp_path, backfill_embeddings=False)
    absolute = tmp_path / "services" / "frontage" / "src" / "routes" / "aipattern.ts"
    ent = store.upsert_entity(
        {
            "name": "Validate",
            "metadata": {"workspace": [{"path": "services/frontage/src/routes/aipattern.ts"}]},
            "code_refs": [{"path": str(absolute)}],
        }
    )
    assert ent["metadata"] == {"workspace": [{"path": "services/frontage/src/routes/aipattern.ts"}]}
    assert ent["code_refs"][0]["path"] == "services/frontage/src/routes/aipattern.ts"
    kept = store.upsert_entity({"name": "Validate", "description": "still grounded"})
    assert kept["metadata"]["workspace"][0]["path"] == "services/frontage/src/routes/aipattern.ts"
    assert kept["description"] == "still grounded"
    with pytest.raises(ValueError, match="valid JSON"):
        store.upsert_entity({"name": "Validate", "metadata": "{not json"})
    store.close()
    assert (
        main(
            [
                "entity",
                "upsert",
                "--name",
                "Validate",
                "--metadata",
                '{"note":"free"}',
                "--path",
                str(tmp_path),
            ]
        )
        == 0
    )
    store = open_store(tmp_path, backfill_embeddings=False)
    assert store.get_entity("Validate")["metadata"] == {"note": "free"}
    store.close()


def test_new_database_schema_version_is_4(tmp_path: Path) -> None:
    _init(tmp_path)
    store = open_store(tmp_path, backfill_embeddings=False)
    version = store._conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    assert version["value"] == "4"
    entity_columns = list(store._conn.execute("PRAGMA table_info(entities)"))
    meta_col = next(info for info in entity_columns if info["name"] == "metadata")
    assert str(meta_col["type"]).upper() == "JSON"
    ref_columns = [info["name"] for info in store._conn.execute("PRAGMA table_info(code_refs)")]
    assert "start_line" in ref_columns
    assert "end_line" in ref_columns
    store.close()


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

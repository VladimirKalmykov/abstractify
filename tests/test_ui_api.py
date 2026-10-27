from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from abstractify.project import init_project
from abstractify.store import open_store
from abstractify.ui_server import build_app


def test_ui_api_create_and_read(tmp_path: Path) -> None:
    init_project(tmp_path, embed_mode="none", example=True)
    store = open_store(tmp_path)
    app = build_app(store)
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    graphs = client.get("/api/graphs").json()["graphs"]
    assert graphs
    detail = client.get(f"/api/graphs/{graphs[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["entities"]
    created = client.post(
        "/api/entities",
        json={"name": "Cache", "description": "in-memory cache", "graph_id": graphs[0]["id"]},
    )
    assert created.status_code == 201
    ents = client.get("/api/entities?q=cache").json()["entities"]
    assert any(e["name"] == "Cache" for e in ents)
    store.close()

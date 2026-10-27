from __future__ import annotations

import json
from pathlib import Path

from abstractify.paths import graphs_dir, snapshots_dir


def write_graph_json(root: Path, graph: dict) -> Path:
    graphs_dir(root).mkdir(parents=True, exist_ok=True)
    path = graphs_dir(root) / f"{graph['id']}.json"
    payload = {"schema_version": 1, "source_of_truth": "sqlite", **graph}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def remove_graph_json(root: Path, graph_id: str) -> None:
    path = graphs_dir(root) / f"{graph_id}.json"
    if path.exists():
        path.unlink()


def write_snapshot_json(root: Path, snapshot: dict) -> Path:
    snapshots_dir(root).mkdir(parents=True, exist_ok=True)
    path = snapshots_dir(root) / f"{snapshot['id']}.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

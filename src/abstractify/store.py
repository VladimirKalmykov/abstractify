from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from abstractify.config import GRAPH_KINDS, KNOWN_RELATIONS, Config
from abstractify.embeddings.base import Embedder
from abstractify.embeddings.none import idf_search
from abstractify.export import remove_graph_json, write_graph_json, write_snapshot_json
from abstractify.paths import db_path, graphs_dir, project_dir, snapshots_dir
from abstractify.size import check_graph_size

try:
    import sqlite_vec
except ImportError:  # pragma: no cover
    sqlite_vec = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    return dict(r)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _ranges_overlap(
    a_start: int | None,
    a_end: int | None,
    b_start: int | None,
    b_end: int | None,
) -> bool:
    if a_start is None and a_end is None:
        return True
    if b_start is None and b_end is None:
        return True
    a0 = a_start if a_start is not None else a_end or 0
    a1 = a_end if a_end is not None else a_start or 10**9
    b0 = b_start if b_start is not None else b_end or 0
    b1 = b_end if b_end is not None else b_start or 10**9
    return a0 <= b1 and b0 <= a1


class Store:
    """SQLite source of truth. JSON files are companion dumps only."""

    def __init__(self, root: Path, cfg: Config, embedder: Embedder) -> None:
        self.root = root.resolve()
        self.cfg = cfg
        self.embedder = embedder
        self._lock = threading.RLock()
        project_dir(self.root).mkdir(parents=True, exist_ok=True)
        graphs_dir(self.root).mkdir(parents=True, exist_ok=True)
        snapshots_dir(self.root).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path(self.root), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._vec_ready = False
        self._vec_dim: int | None = None
        self._init_schema()
        self._try_load_sqlite_vec()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        sql = resources.files("abstractify").joinpath("schema.sql").read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(sql)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '1')"
            )
            self._conn.commit()

    def _try_load_sqlite_vec(self) -> None:
        if sqlite_vec is None:
            return
        try:
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._vec_ready = True
        except Exception:
            self._vec_ready = False

    def _ensure_vec_table(self, dim: int) -> None:
        if not self._vec_ready:
            return
        if self._vec_dim == dim:
            return
        self._conn.execute("DROP TABLE IF EXISTS vec_entities")
        self._conn.execute(
            f"CREATE VIRTUAL TABLE vec_entities USING vec0("
            f"entity_id TEXT PRIMARY KEY, embedding FLOAT[{dim}])"
        )
        self._vec_dim = dim
        rows = self._conn.execute("SELECT entity_id, vector_json, dim FROM entity_embeddings").fetchall()
        for row in rows:
            if row["dim"] != dim:
                continue
            vec = json.loads(row["vector_json"])
            self._conn.execute(
                "INSERT INTO vec_entities(entity_id, embedding) VALUES (?, ?)",
                (row["entity_id"], json.dumps(vec)),
            )

    # --- graphs ---

    def list_graphs(self, kind: str | None = None) -> list[dict]:
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM graphs WHERE kind = ? ORDER BY name COLLATE NOCASE",
                    (kind,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM graphs ORDER BY name COLLATE NOCASE"
                ).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item["entity_count"] = self._conn.execute(
                    "SELECT COUNT(*) FROM graph_entities WHERE graph_id = ?",
                    (item["id"],),
                ).fetchone()[0]
                item["edge_count"] = self._conn.execute(
                    "SELECT COUNT(*) FROM edges WHERE graph_id = ?",
                    (item["id"],),
                ).fetchone()[0]
                out.append(item)
            return out

    def get_graph(self, graph_id: str, *, include_contents: bool = True) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM graphs WHERE id = ?", (graph_id,)).fetchone()
            if row is None:
                row = self._conn.execute(
                    "SELECT * FROM graphs WHERE name = ? COLLATE NOCASE", (graph_id,)
                ).fetchone()
            if row is None:
                return None
            graph = dict(row)
            if not include_contents:
                return graph
            eids = [
                r[0]
                for r in self._conn.execute(
                    "SELECT entity_id FROM graph_entities WHERE graph_id = ?",
                    (graph["id"],),
                ).fetchall()
            ]
            graph["entities"] = [self._entity_payload(eid) for eid in eids]
            graph["edges"] = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM edges WHERE graph_id = ? ORDER BY created_at",
                    (graph["id"],),
                ).fetchall()
            ]
            return graph

    def create_graph(
        self,
        *,
        name: str,
        kind: str,
        principle: str,
        description: str = "",
        entities: list[dict] | None = None,
        edges: list[dict] | None = None,
        confirm_large: bool = False,
        graph_id: str | None = None,
    ) -> dict:
        if kind not in GRAPH_KINDS:
            raise ValueError(f"kind must be one of {GRAPH_KINDS}")
        gid = graph_id or _id("g")
        n_ent = len(entities or [])
        n_edge = len(edges or [])
        check_graph_size(
            graph_id=gid,
            entity_count=n_ent,
            edge_count=n_edge,
            cfg=self.cfg,
            confirm_large=confirm_large,
        )
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO graphs(id, name, kind, principle, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gid, name, kind, principle, description, now, now),
            )
            id_map: dict[str, str] = {}
            for spec in entities or []:
                ent = self._upsert_entity_locked(spec, graph_id=gid)
                if spec.get("id"):
                    id_map[str(spec["id"])] = ent["id"]
                id_map[ent["name"].lower()] = ent["id"]
            for spec in edges or []:
                self._upsert_edge_locked(gid, spec, id_map=id_map)
            self._conn.commit()
        graph = self.get_graph(gid)
        assert graph is not None
        write_graph_json(self.root, graph)
        return graph

    def update_graph(
        self,
        graph_id: str,
        *,
        name: str | None = None,
        kind: str | None = None,
        principle: str | None = None,
        description: str | None = None,
        entities: list[dict] | None = None,
        edges: list[dict] | None = None,
        confirm_large: bool = False,
    ) -> dict:
        graph = self.get_graph(graph_id, include_contents=False)
        if graph is None:
            raise KeyError(f"graph not found: {graph_id}")
        gid = graph["id"]
        if kind is not None and kind not in GRAPH_KINDS:
            raise ValueError(f"kind must be one of {GRAPH_KINDS}")
        n_ent = len(entities) if entities is not None else self._count_entities(gid)
        n_edge = len(edges) if edges is not None else self._count_edges(gid)
        check_graph_size(
            graph_id=gid,
            entity_count=n_ent,
            edge_count=n_edge,
            cfg=self.cfg,
            confirm_large=confirm_large,
        )
        now = _now()
        with self._lock:
            if name is not None:
                graph["name"] = name
            if kind is not None:
                graph["kind"] = kind
            if principle is not None:
                graph["principle"] = principle
            if description is not None:
                graph["description"] = description
            self._conn.execute(
                "UPDATE graphs SET name=?, kind=?, principle=?, description=?, updated_at=? WHERE id=?",
                (graph["name"], graph["kind"], graph["principle"], graph["description"], now, gid),
            )
            id_map: dict[str, str] = {}
            if entities is not None:
                self._conn.execute("DELETE FROM graph_entities WHERE graph_id = ?", (gid,))
                for spec in entities:
                    ent = self._upsert_entity_locked(spec, graph_id=gid)
                    if spec.get("id"):
                        id_map[str(spec["id"])] = ent["id"]
                    id_map[ent["name"].lower()] = ent["id"]
            if edges is not None:
                self._conn.execute("DELETE FROM edges WHERE graph_id = ?", (gid,))
                for spec in edges:
                    self._upsert_edge_locked(gid, spec, id_map=id_map)
            self._conn.commit()
        full = self.get_graph(gid)
        assert full is not None
        write_graph_json(self.root, full)
        return full

    def delete_graph(self, graph_id: str) -> bool:
        graph = self.get_graph(graph_id, include_contents=False)
        if graph is None:
            return False
        with self._lock:
            self._conn.execute("DELETE FROM graphs WHERE id = ?", (graph["id"],))
            self._conn.commit()
        remove_graph_json(self.root, graph["id"])
        return True

    def _count_entities(self, graph_id: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM graph_entities WHERE graph_id = ?", (graph_id,)
            ).fetchone()[0]

    def _count_edges(self, graph_id: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM edges WHERE graph_id = ?", (graph_id,)
            ).fetchone()[0]

    # --- entities ---

    def list_entities(self, query: str | None = None, graph_id: str | None = None) -> list[dict]:
        with self._lock:
            if graph_id:
                rows = self._conn.execute(
                    "SELECT e.* FROM entities e "
                    "JOIN graph_entities ge ON ge.entity_id = e.id "
                    "WHERE ge.graph_id = ? ORDER BY e.name COLLATE NOCASE",
                    (graph_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM entities ORDER BY name COLLATE NOCASE"
                ).fetchall()
            items = [self._entity_payload(r["id"]) for r in rows]
        if query:
            return idf_search(query, items, k=len(items) or 1)
        return items

    def get_entity(self, entity_id: str) -> dict | None:
        with self._lock:
            return self._entity_payload(entity_id) if self._resolve_entity_id(entity_id) else None

    def upsert_entity(self, spec: dict, *, graph_id: str | None = None, confirm_large: bool = False) -> dict:
        gid = None
        if graph_id:
            graph = self.get_graph(graph_id, include_contents=False)
            if graph is None:
                raise KeyError(f"graph not found: {graph_id}")
            gid = graph["id"]
            existing = self._resolve_entity_id(spec.get("id") or spec.get("name") or "")
            already = False
            if existing:
                with self._lock:
                    already = self._conn.execute(
                        "SELECT 1 FROM graph_entities WHERE graph_id=? AND entity_id=?",
                        (gid, existing),
                    ).fetchone() is not None
            if not already:
                check_graph_size(
                    graph_id=gid,
                    entity_count=self._count_entities(gid) + 1,
                    edge_count=self._count_edges(gid),
                    cfg=self.cfg,
                    confirm_large=confirm_large,
                )
        with self._lock:
            ent = self._upsert_entity_locked(spec, graph_id=gid)
            self._conn.commit()
        self._sync_graphs_touching(ent["id"])
        return self.get_entity(ent["id"])  # type: ignore[return-value]

    def delete_entity(self, entity_id: str) -> bool:
        eid = self._resolve_entity_id(entity_id)
        if not eid:
            return False
        graphs = self._graphs_for_entity(eid)
        with self._lock:
            self._conn.execute("DELETE FROM entities WHERE id = ?", (eid,))
            self._conn.commit()
        for g in graphs:
            full = self.get_graph(g)
            if full:
                write_graph_json(self.root, full)
        return True

    def _upsert_entity_locked(self, spec: dict, graph_id: str | None = None) -> dict:
        name = (spec.get("name") or "").strip()
        if not name:
            raise ValueError("entity name is required")
        description = spec.get("description") or ""
        now = _now()
        eid = spec.get("id")
        existing = None
        if eid:
            existing = self._conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
        if existing is None:
            by_name = self._conn.execute(
                "SELECT * FROM entities WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if by_name is not None and not eid:
                existing = by_name
                eid = by_name["id"]
        if existing is None:
            eid = eid or _id("e")
            self._conn.execute(
                "INSERT INTO entities(id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (eid, name, description, now, now),
            )
        else:
            eid = existing["id"]
            if spec.get("name") or spec.get("description") is not None:
                self._conn.execute(
                    "UPDATE entities SET name=?, description=?, updated_at=? WHERE id=?",
                    (
                        name or existing["name"],
                        description if "description" in spec else existing["description"],
                        now,
                        eid,
                    ),
                )
        if graph_id:
            self._conn.execute(
                "INSERT OR IGNORE INTO graph_entities(graph_id, entity_id) VALUES (?, ?)",
                (graph_id, eid),
            )
        if "code_refs" in spec:
            self._conn.execute("DELETE FROM code_refs WHERE entity_id = ?", (eid,))
            for ref in spec.get("code_refs") or []:
                self._insert_code_ref_locked(eid, ref)
        elif spec.get("add_code_refs"):
            for ref in spec["add_code_refs"]:
                self._insert_code_ref_locked(eid, ref)
        self._embed_entity_locked(eid)
        return dict(self._conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone())

    def _insert_code_ref_locked(self, entity_id: str, ref: dict) -> None:
        path = _norm_path(ref.get("path") or "")
        if not path:
            raise ValueError("code_ref.path is required")
        self._conn.execute(
            "INSERT INTO code_refs(id, entity_id, path, start_line, end_line, note) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _id("c"),
                entity_id,
                path,
                ref.get("start_line"),
                ref.get("end_line"),
                ref.get("note") or "",
            ),
        )

    def add_code_ref(self, entity_id: str, ref: dict) -> dict:
        eid = self._require_entity(entity_id)
        with self._lock:
            self._insert_code_ref_locked(eid, ref)
            self._conn.commit()
        self._sync_graphs_touching(eid)
        return self.get_entity(eid)  # type: ignore[return-value]

    def _entity_payload(self, entity_id: str) -> dict:
        eid = self._resolve_entity_id(entity_id)
        if not eid:
            raise KeyError(entity_id)
        ent = dict(self._conn.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone())
        ent["code_refs"] = [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM code_refs WHERE entity_id = ? ORDER BY path", (eid,)
            ).fetchall()
        ]
        ent["meta_links"] = [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM meta_links WHERE entity_id = ? OR related_entity_id = ?",
                (eid, eid),
            ).fetchall()
        ]
        ent["graphs"] = [
            dict(r)
            for r in self._conn.execute(
                "SELECT g.id, g.name, g.kind, g.principle FROM graphs g "
                "JOIN graph_entities ge ON ge.graph_id = g.id WHERE ge.entity_id = ?",
                (eid,),
            ).fetchall()
        ]
        ent["degree"] = self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE source_id = ? OR target_id = ?",
            (eid, eid),
        ).fetchone()[0]
        ent["code_ref_count"] = len(ent["code_refs"])
        ent["meta_link_count"] = len(ent["meta_links"])
        return ent

    def _resolve_entity_id(self, token: str) -> str | None:
        if not token:
            return None
        row = self._conn.execute("SELECT id FROM entities WHERE id = ?", (token,)).fetchone()
        if row:
            return row[0]
        row = self._conn.execute(
            "SELECT id FROM entities WHERE name = ? COLLATE NOCASE", (token,)
        ).fetchone()
        return row[0] if row else None

    def _require_entity(self, token: str) -> str:
        with self._lock:
            eid = self._resolve_entity_id(token)
        if not eid:
            raise KeyError(f"entity not found: {token}")
        return eid

    def _graphs_for_entity(self, eid: str) -> list[str]:
        with self._lock:
            return [
                r[0]
                for r in self._conn.execute(
                    "SELECT graph_id FROM graph_entities WHERE entity_id = ?", (eid,)
                ).fetchall()
            ]

    def _sync_graphs_touching(self, eid: str) -> None:
        for gid in self._graphs_for_entity(eid):
            full = self.get_graph(gid)
            if full:
                write_graph_json(self.root, full)

    # --- edges ---

    def upsert_edge(self, graph_id: str, spec: dict, *, confirm_large: bool = False) -> dict:
        graph = self.get_graph(graph_id, include_contents=False)
        if graph is None:
            raise KeyError(f"graph not found: {graph_id}")
        gid = graph["id"]
        existing_id = spec.get("id")
        replacing = False
        if existing_id:
            with self._lock:
                replacing = (
                    self._conn.execute("SELECT 1 FROM edges WHERE id = ?", (existing_id,)).fetchone()
                    is not None
                )
        if not replacing:
            check_graph_size(
                graph_id=gid,
                entity_count=self._count_entities(gid),
                edge_count=self._count_edges(gid) + 1,
                cfg=self.cfg,
                confirm_large=confirm_large,
            )
        with self._lock:
            edge = self._upsert_edge_locked(gid, spec)
            self._conn.commit()
        full = self.get_graph(gid)
        if full:
            write_graph_json(self.root, full)
        return edge

    def delete_edge(self, edge_id: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT graph_id FROM edges WHERE id = ?", (edge_id,)).fetchone()
            if row is None:
                return False
            gid = row[0]
            self._conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
            self._conn.commit()
        full = self.get_graph(gid)
        if full:
            write_graph_json(self.root, full)
        return True

    def _upsert_edge_locked(
        self, graph_id: str, spec: dict, id_map: dict[str, str] | None = None
    ) -> dict:
        def resolve(token: str) -> str:
            token = str(token)
            if id_map:
                if token in id_map:
                    return id_map[token]
                if token.lower() in id_map:
                    return id_map[token.lower()]
            eid = self._resolve_entity_id(token)
            if not eid:
                raise KeyError(f"entity not found for edge endpoint: {token}")
            return eid

        source = resolve(spec.get("source") or spec.get("source_id") or "")
        target = resolve(spec.get("target") or spec.get("target_id") or "")
        relation = spec.get("relation") or "knows_about"
        kind = spec.get("kind") or self._conn.execute(
            "SELECT kind FROM graphs WHERE id = ?", (graph_id,)
        ).fetchone()[0]
        if kind not in ("structural", "flow", "meta"):
            raise ValueError("edge kind must be structural, flow, or meta")
        now = _now()
        eid = spec.get("id")
        existing = None
        if eid:
            existing = self._conn.execute("SELECT * FROM edges WHERE id = ?", (eid,)).fetchone()
        metadata = spec.get("metadata") or {}
        if isinstance(metadata, dict):
            metadata_s = json.dumps(metadata)
        else:
            metadata_s = str(metadata)
        if existing is None:
            eid = eid or _id("d")
            self._conn.execute(
                "INSERT INTO edges(id, graph_id, source_id, target_id, relation, kind, metadata, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, graph_id, source, target, relation, kind, metadata_s, now, now),
            )
        else:
            eid = existing["id"]
            self._conn.execute(
                "UPDATE edges SET source_id=?, target_id=?, relation=?, kind=?, metadata=?, updated_at=? WHERE id=?",
                (source, target, relation, kind, metadata_s, now, eid),
            )
        self._conn.execute(
            "INSERT OR IGNORE INTO graph_entities(graph_id, entity_id) VALUES (?, ?)",
            (graph_id, source),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO graph_entities(graph_id, entity_id) VALUES (?, ?)",
            (graph_id, target),
        )
        return dict(self._conn.execute("SELECT * FROM edges WHERE id = ?", (eid,)).fetchone())

    # --- meta-links ---

    def add_meta_link(
        self,
        entity_id: str,
        related_entity_id: str,
        relation: str,
        note: str = "",
    ) -> dict:
        a = self._require_entity(entity_id)
        b = self._require_entity(related_entity_id)
        mid = _id("m")
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta_links(id, entity_id, related_entity_id, relation, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, a, b, relation, note, now),
            )
            self._conn.commit()
        self._sync_graphs_touching(a)
        self._sync_graphs_touching(b)
        with self._lock:
            return dict(self._conn.execute("SELECT * FROM meta_links WHERE id = ?", (mid,)).fetchone())

    def delete_meta_link(self, meta_id: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT * FROM meta_links WHERE id = ?", (meta_id,)).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM meta_links WHERE id = ?", (meta_id,))
            self._conn.commit()
            a, b = row["entity_id"], row["related_entity_id"]
        self._sync_graphs_touching(a)
        self._sync_graphs_touching(b)
        return True

    # --- reverse index / affected ---

    def lookup_by_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> list[dict]:
        needle = _norm_path(path)
        with self._lock:
            rows = self._conn.execute("SELECT * FROM code_refs").fetchall()
            matched_ids: list[str] = []
            refs_by_entity: dict[str, list[dict]] = {}
            for r in rows:
                stored = _norm_path(r["path"])
                if not _path_match(needle, stored):
                    continue
                if not _ranges_overlap(start_line, end_line, r["start_line"], r["end_line"]):
                    continue
                matched_ids.append(r["entity_id"])
                refs_by_entity.setdefault(r["entity_id"], []).append(dict(r))
        entities = []
        seen = set()
        for eid in matched_ids:
            if eid in seen:
                continue
            seen.add(eid)
            payload = self.get_entity(eid)
            if payload:
                payload["matched_code_refs"] = refs_by_entity.get(eid, [])
                entities.append(payload)
        return entities

    def affected_by_files(self, files: list[str]) -> dict:
        entities: dict[str, dict] = {}
        graphs: dict[str, dict] = {}
        for path in files:
            for ent in self.lookup_by_file(path):
                entities[ent["id"]] = ent
                for g in ent.get("graphs") or []:
                    graphs[g["id"]] = g
        return {
            "files": files,
            "entities": list(entities.values()),
            "graphs": list(graphs.values()),
            "note": "Verify these abstractions. Abstractify does not auto-mutate.",
        }

    # --- search / path / explain ---

    def search(self, query: str, k: int = 20, semantic: bool = True) -> dict:
        items = self.list_entities()
        text_hits = idf_search(query, items, k=k)
        semantic_hits: list[dict] = []
        used = "text_idf"
        if semantic and self.cfg.embed_mode != "none":
            custom = self.embedder.retrieve(query, items, k)
            if custom is not None:
                semantic_hits = custom
                used = f"custom:{self.embedder.name}"
            else:
                semantic_hits = self._vector_search(query, items, k)
                used = f"vector:{self.embedder.name}" if semantic_hits else "text_idf"
        # merge: semantic first if present, else text
        merged: dict[str, dict] = {}
        for src in (semantic_hits, text_hits):
            for it in src:
                merged.setdefault(it["id"], it)
        hits = list(merged.values())[:k]
        return {"query": query, "mode": used, "hits": hits}

    def _vector_search(self, query: str, items: list[dict], k: int) -> list[dict]:
        try:
            qvec = self.embedder.embed([query])[0]
        except Exception:
            return []
        if not qvec:
            return []
        scored: list[tuple[float, dict]] = []
        with self._lock:
            rows = self._conn.execute("SELECT entity_id, vector_json FROM entity_embeddings").fetchall()
            by_id = {it["id"]: it for it in items}
            for row in rows:
                vec = json.loads(row["vector_json"])
                if not vec:
                    continue
                item = by_id.get(row["entity_id"])
                if not item:
                    continue
                scored.append((_cosine(qvec, vec), item))
        scored.sort(key=lambda x: -x[0])
        return [it for s, it in scored[:k] if s > 0]

    def shortest_path(
        self,
        source: str,
        target: str,
        *,
        graph_id: str | None = None,
        undirected: bool = True,
    ) -> dict:
        src = self._require_entity(source)
        dst = self._require_entity(target)
        with self._lock:
            if graph_id:
                edges = [
                    dict(r)
                    for r in self._conn.execute(
                        "SELECT * FROM edges WHERE graph_id = ?", (graph_id,)
                    ).fetchall()
                ]
            else:
                edges = [dict(r) for r in self._conn.execute("SELECT * FROM edges").fetchall()]
        adj: dict[str, list[tuple[str, dict]]] = {}
        for e in edges:
            adj.setdefault(e["source_id"], []).append((e["target_id"], e))
            if undirected:
                adj.setdefault(e["target_id"], []).append((e["source_id"], e))
        prev: dict[str, tuple[str, dict] | None] = {src: None}
        queue = [src]
        found = src == dst
        while queue and not found:
            node = queue.pop(0)
            for nxt, edge in adj.get(node, []):
                if nxt in prev:
                    continue
                prev[nxt] = (node, edge)
                if nxt == dst:
                    found = True
                    break
                queue.append(nxt)
        if dst not in prev:
            return {"source": src, "target": dst, "found": False, "nodes": [], "edges": []}
        nodes = [dst]
        edges_out: list[dict] = []
        cur = dst
        while prev[cur] is not None:
            parent, edge = prev[cur]  # type: ignore[misc]
            edges_out.append(edge)
            nodes.append(parent)
            cur = parent
        nodes.reverse()
        edges_out.reverse()
        return {
            "source": src,
            "target": dst,
            "found": True,
            "nodes": [self.get_entity(n) for n in nodes],
            "edges": edges_out,
        }

    def explain(self, entity_id: str) -> dict:
        ent = self.get_entity(entity_id)
        if ent is None:
            raise KeyError(f"entity not found: {entity_id}")
        with self._lock:
            neighbors = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM edges WHERE source_id = ? OR target_id = ?",
                    (ent["id"], ent["id"]),
                ).fetchall()
            ]
        neighbor_ids = set()
        for e in neighbors:
            neighbor_ids.add(e["source_id"])
            neighbor_ids.add(e["target_id"])
        neighbor_ids.discard(ent["id"])
        return {
            "entity": ent,
            "neighbors": [self.get_entity(i) for i in neighbor_ids],
            "edges": neighbors,
            "graphs": ent.get("graphs") or [],
        }

    # --- snapshots ---

    def create_snapshot(self, graph_id: str, label: str = "") -> dict:
        graph = self.get_graph(graph_id)
        if graph is None:
            raise KeyError(f"graph not found: {graph_id}")
        sid = _id("s")
        now = _now()
        payload = json.dumps(graph, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots(id, graph_id, label, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (sid, graph["id"], label, payload, now),
            )
            self._conn.commit()
        snap = {
            "id": sid,
            "graph_id": graph["id"],
            "label": label,
            "payload": graph,
            "created_at": now,
        }
        write_snapshot_json(self.root, snap)
        return snap

    def list_snapshots(self, graph_id: str | None = None) -> list[dict]:
        with self._lock:
            if graph_id:
                rows = self._conn.execute(
                    "SELECT id, graph_id, label, created_at FROM snapshots WHERE graph_id = ? ORDER BY created_at DESC",
                    (graph_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, graph_id, label, created_at FROM snapshots ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    def restore_snapshot(self, snapshot_id: str, *, confirm_large: bool = False) -> dict:
        snap = self.get_snapshot(snapshot_id)
        if snap is None:
            raise KeyError(f"snapshot not found: {snapshot_id}")
        payload = snap["payload"]
        return self.update_graph(
            payload["id"],
            name=payload.get("name"),
            kind=payload.get("kind"),
            principle=payload.get("principle"),
            description=payload.get("description"),
            entities=payload.get("entities") or [],
            edges=payload.get("edges") or [],
            confirm_large=confirm_large,
        )

    # --- embeddings ---

    def _embed_entity_locked(self, entity_id: str) -> None:
        if self.cfg.embed_mode == "none":
            return
        row = self._conn.execute(
            "SELECT name, description FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            return
        text = f"{row['name']}. {row['description']}".strip()
        try:
            vec = self.embedder.embed([text])[0]
        except Exception:
            return
        if not vec:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO entity_embeddings(entity_id, dim, vector_json, model) VALUES (?, ?, ?, ?)",
            (entity_id, len(vec), json.dumps(vec), self.embedder.name),
        )
        try:
            self._ensure_vec_table(len(vec))
            if self._vec_ready and self._vec_dim == len(vec):
                self._conn.execute("DELETE FROM vec_entities WHERE entity_id = ?", (entity_id,))
                self._conn.execute(
                    "INSERT INTO vec_entities(entity_id, embedding) VALUES (?, ?)",
                    (entity_id, json.dumps(vec)),
                )
        except Exception:
            pass

    # --- example ---

    def seed_example(self) -> dict:
        return self.create_graph(
            name="Core services",
            kind="structural",
            principle="Group components by how they talk to each other over the network.",
            description="Example structural slice — replace with a real user-defined principle.",
            entities=[
                {
                    "name": "API Gateway",
                    "description": "Entry point that routes external requests.",
                    "code_refs": [{"path": "src/gateway.py", "start_line": 1, "end_line": 80}],
                },
                {
                    "name": "Auth Service",
                    "description": "Issues and verifies credentials.",
                    "code_refs": [{"path": "src/auth/service.py", "start_line": 10, "end_line": 120}],
                },
                {
                    "name": "Data Store",
                    "description": "Persists project records.",
                    "code_refs": [{"path": "src/store.py"}],
                },
            ],
            edges=[
                {"source": "API Gateway", "target": "Auth Service", "relation": "calls"},
                {"source": "API Gateway", "target": "Data Store", "relation": "knows_about"},
                {
                    "source": "Auth Service",
                    "target": "Data Store",
                    "relation": "does_not_know_about",
                },
            ],
        )


def _path_match(query: str, stored: str) -> bool:
    q = query.lower()
    s = stored.lower()
    if q == s:
        return True
    if s.endswith("/" + q) or q.endswith("/" + s):
        return True
    if q in s or s in q:
        # avoid matching tiny accidental substrings
        if min(len(q), len(s)) >= 4:
            return True
    return Path(s).name.lower() == Path(q).name.lower() and Path(q).name != ""


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def open_store(root: Path) -> Store:
    from abstractify.config import load_config
    from abstractify.embeddings import build_embedder

    cfg = load_config(root)
    return Store(root, cfg, build_embedder(cfg, root))

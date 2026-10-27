from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from abstractify.size import GraphTooLarge
from abstractify.store import Store, open_store

INSTRUCTIONS = """\
Abstractify stores user-defined abstraction graphs (structural and flow) in SQLite.
You (the agent) decide what to abstract — do not auto-mutate after code edits.
After finishing an edit, call affected_by_files or lookup_by_file, read the graphs, and verify.
Record a user-defined principle on every graph you create.
If a graph is too large, ask the user before retrying with confirm_large=true.
"""


def _ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def _err(exc: Exception) -> dict:
    if isinstance(exc, GraphTooLarge):
        return exc.as_dict()
    return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


def build_server(store: Store) -> MCPServer:
    server = MCPServer(
        name="abstractify",
        version="0.1.0",
        instructions=INSTRUCTIONS,
    )

    @server.tool(description="List graphs in the registry. Optional kind filter: structural | flow.")
    def list_graphs(kind: str | None = None) -> dict:
        try:
            return _ok(store.list_graphs(kind=kind))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Get one graph with entities and edges (SQLite, not JSON-on-disk).")
    def get_graph(graph_id: str) -> dict:
        try:
            graph = store.get_graph(graph_id)
            if graph is None:
                return _err(KeyError(f"graph not found: {graph_id}"))
            return _ok(graph)
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Create a graph. principle is the user-defined abstraction principle (required). "
        "kind is structural or flow. Optional entities/edges. Size guard: confirm_large."
    )
    def create_graph(
        name: str,
        kind: str,
        principle: str,
        description: str = "",
        entities: list[dict] | None = None,
        edges: list[dict] | None = None,
        confirm_large: bool = False,
    ) -> dict:
        try:
            return _ok(
                store.create_graph(
                    name=name,
                    kind=kind,
                    principle=principle,
                    description=description,
                    entities=entities,
                    edges=edges,
                    confirm_large=confirm_large,
                )
            )
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Update graph metadata and/or replace entities/edges (whole-graph update). "
        "Prefer targeted entity/edge tools for small edits."
    )
    def update_graph(
        graph_id: str,
        name: str | None = None,
        kind: str | None = None,
        principle: str | None = None,
        description: str | None = None,
        entities: list[dict] | None = None,
        edges: list[dict] | None = None,
        confirm_large: bool = False,
    ) -> dict:
        try:
            return _ok(
                store.update_graph(
                    graph_id,
                    name=name,
                    kind=kind,
                    principle=principle,
                    description=description,
                    entities=entities,
                    edges=edges,
                    confirm_large=confirm_large,
                )
            )
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Delete a graph from the registry.")
    def delete_graph(graph_id: str) -> dict:
        try:
            return _ok({"deleted": store.delete_graph(graph_id)})
        except Exception as exc:
            return _err(exc)

    @server.tool(description="List entities, optionally filtered by search query or graph.")
    def list_entities(query: str | None = None, graph_id: str | None = None) -> dict:
        try:
            return _ok(store.list_entities(query=query, graph_id=graph_id))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Get one entity: description, code refs, meta-links, graphs.")
    def get_entity(entity_id: str) -> dict:
        try:
            ent = store.get_entity(entity_id)
            if ent is None:
                return _err(KeyError(f"entity not found: {entity_id}"))
            return _ok(ent)
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Create or update a specific entity (targeted edit). "
        "code_refs: [{path, start_line?, end_line?, note?}]. Optional graph_id membership."
    )
    def upsert_entity(
        name: str,
        description: str = "",
        entity_id: str | None = None,
        graph_id: str | None = None,
        code_refs: list[dict] | None = None,
        confirm_large: bool = False,
    ) -> dict:
        spec: dict = {"name": name, "description": description}
        if entity_id:
            spec["id"] = entity_id
        if code_refs is not None:
            spec["code_refs"] = code_refs
        try:
            return _ok(store.upsert_entity(spec, graph_id=graph_id, confirm_large=confirm_large))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Delete an entity from the registry (all graphs).")
    def delete_entity(entity_id: str) -> dict:
        try:
            return _ok({"deleted": store.delete_entity(entity_id)})
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Create or update a specific edge in a graph (targeted edit). "
        "relation: knows_about | does_not_know_about | calls | responds_to | custom."
    )
    def upsert_edge(
        graph_id: str,
        source: str,
        target: str,
        relation: str = "knows_about",
        kind: str | None = None,
        edge_id: str | None = None,
        confirm_large: bool = False,
    ) -> dict:
        spec: dict = {"source": source, "target": target, "relation": relation}
        if kind:
            spec["kind"] = kind
        if edge_id:
            spec["id"] = edge_id
        try:
            return _ok(store.upsert_edge(graph_id, spec, confirm_large=confirm_large))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Delete a specific edge by id.")
    def delete_edge(edge_id: str) -> dict:
        try:
            return _ok({"deleted": store.delete_edge(edge_id)})
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Add a meta-link (relationship) for an entity, possibly cross-graph. "
        "Distinct from ordinary graph edges."
    )
    def add_meta_link(
        entity_id: str,
        related_entity_id: str,
        relation: str,
        note: str = "",
    ) -> dict:
        try:
            return _ok(store.add_meta_link(entity_id, related_entity_id, relation, note))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Delete a meta-link by id.")
    def delete_meta_link(meta_id: str) -> dict:
        try:
            return _ok({"deleted": store.delete_meta_link(meta_id)})
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Reverse index: given a file (and optional line range), return all abstractions that reference it."
    )
    def lookup_by_file(
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict:
        try:
            return _ok(store.lookup_by_file(path, start_line, end_line))
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="After an edit: files that changed → linked entities and graphs. "
        "Does not mutate. Agent must verify."
    )
    def affected_by_files(files: list[str]) -> dict:
        try:
            return _ok(store.affected_by_files(files))
        except Exception as exc:
            return _err(exc)

    @server.tool(
        description="Search entities by name (text) and description (semantic when embeddings are enabled)."
    )
    def search(query: str, k: int = 20, semantic: bool = True) -> dict:
        try:
            return _ok(store.search(query, k=k, semantic=semantic))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="How two abstractions are connected (shortest path).")
    def path(
        source: str,
        target: str,
        graph_id: str | None = None,
        undirected: bool = True,
    ) -> dict:
        try:
            return _ok(
                store.shortest_path(source, target, graph_id=graph_id, undirected=undirected)
            )
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Explain one abstraction: description, code grounding, neighbors, graphs.")
    def explain(entity_id: str) -> dict:
        try:
            return _ok(store.explain(entity_id))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Snapshot a graph (version it after agent writes).")
    def create_snapshot(graph_id: str, label: str = "") -> dict:
        try:
            return _ok(store.create_snapshot(graph_id, label=label))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="List graph snapshots.")
    def list_snapshots(graph_id: str | None = None) -> dict:
        try:
            return _ok(store.list_snapshots(graph_id=graph_id))
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Read a snapshot payload.")
    def get_snapshot(snapshot_id: str) -> dict:
        try:
            snap = store.get_snapshot(snapshot_id)
            if snap is None:
                return _err(KeyError(f"snapshot not found: {snapshot_id}"))
            return _ok(snap)
        except Exception as exc:
            return _err(exc)

    @server.tool(description="Restore a graph from a snapshot (write).")
    def restore_snapshot(snapshot_id: str, confirm_large: bool = False) -> dict:
        try:
            return _ok(store.restore_snapshot(snapshot_id, confirm_large=confirm_large))
        except Exception as rest_exc:
            return _err(rest_exc)

    return server


def run_mcp(
    root: Path,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int | None = None,
) -> None:
    store = open_store(root)
    server = build_server(store)
    if transport == "http":
        listen = port or store.cfg.mcp_port
        import sys

        import uvicorn

        from abstractify.activity import ActivityASGI

        print(
            f"abstractify serve: MCP server started (http {host}:{listen})",
            file=sys.stderr,
        )
        app = ActivityASGI(server.streamable_http_app(host=host), store.root)
        uvicorn.run(app, host=host, port=listen, log_level="warning")
    else:
        import asyncio
        import sys

        print("abstractify serve: MCP server started (stdio)", file=sys.stderr)
        asyncio.run(server.run_stdio_async())

from __future__ import annotations

import json
import mimetypes
import webbrowser
from importlib import resources
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from abstractify.activity import ActivityASGI
from abstractify.size import GraphTooLarge
from abstractify.store import Store, open_store


def _json_error(exc: Exception, status: int = 400) -> JSONResponse:
    if isinstance(exc, GraphTooLarge):
        return JSONResponse(exc.as_dict(), status_code=409)
    if isinstance(exc, KeyError):
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=status)


def build_app(store: Store) -> Starlette:
    ui_dist = Path(__file__).resolve().parent / "ui" / "dist"

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "embed_mode": store.cfg.embed_mode})

    async def api_graphs(request: Request) -> JSONResponse:
        kind = request.query_params.get("kind")
        return JSONResponse({"graphs": store.list_graphs(kind=kind or None)})

    async def api_graph(request: Request) -> JSONResponse:
        graph = store.get_graph(request.path_params["graph_id"])
        if graph is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(graph)

    async def api_create_graph(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            graph = store.create_graph(
                name=body["name"],
                kind=body.get("kind", "structural"),
                principle=body.get("principle", ""),
                description=body.get("description", ""),
                confirm_large=bool(body.get("confirm_large")),
            )
            return JSONResponse(graph, status_code=201)
        except Exception as exc:
            return _json_error(exc)

    async def api_entities(request: Request) -> JSONResponse:
        q = request.query_params.get("q")
        gid = request.query_params.get("graph")
        return JSONResponse({"entities": store.list_entities(query=q, graph_id=gid)})

    async def api_create_entity(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            spec: dict = {
                "name": body["name"],
                "description": body.get("description", ""),
                "code_refs": body.get("code_refs") or [],
            }
            if "metadata" in body:
                spec["metadata"] = body["metadata"]
            ent = store.upsert_entity(
                spec,
                graph_id=body.get("graph_id"),
            )
            return JSONResponse(ent, status_code=201)
        except Exception as exc:
            return _json_error(exc)

    async def api_config(_request: Request) -> JSONResponse:
        cfg = store.cfg
        return JSONResponse(
            {
                "embed_mode": cfg.embed_mode,
                "max_entities_per_graph": cfg.max_entities_per_graph,
                "max_edges_per_graph": cfg.max_edges_per_graph,
                "relations": ["knows_about", "does_not_know_about", "calls", "responds_to"],
            }
        )

    async def spa(request: Request) -> Response:
        rel = request.path_params.get("path", "") or "index.html"
        if rel in ("", "/"):
            rel = "index.html"
        candidate = (ui_dist / rel).resolve()
        try:
            candidate.relative_to(ui_dist.resolve())
        except ValueError:
            return JSONResponse({"error": "not found"}, status_code=404)
        if candidate.is_file():
            mime, _ = mimetypes.guess_type(str(candidate))
            return FileResponse(candidate, media_type=mime)
        index = ui_dist / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        # Fallback: package a tiny page if dist is missing
        html = resources.files("abstractify").joinpath("ui/index.html")
        if html.is_file():  # type: ignore[attr-defined]
            return FileResponse(Path(str(html)), media_type="text/html")
        return Response(
            "<!doctype html><meta charset=utf-8><title>Abstractify</title>"
            "<body style='background:#070b12;color:#20e3c8;font-family:sans-serif'>"
            "<p>UI dist not built. From abstractify/ui run: npm install && npm run build</p>",
            media_type="text/html",
        )

    routes = [
        Route("/api/health", health),
        Route("/api/config", api_config),
        Route("/api/graphs", api_graphs, methods=["GET"]),
        Route("/api/graphs", api_create_graph, methods=["POST"]),
        Route("/api/graphs/{graph_id}", api_graph),
        Route("/api/entities", api_entities, methods=["GET"]),
        Route("/api/entities", api_create_entity, methods=["POST"]),
        Route("/", spa),
        Route("/{path:path}", spa),
    ]
    return Starlette(debug=False, routes=routes)


def run_ui(
    root: Path,
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = False,
) -> None:
    store = open_store(root)
    host = host or store.cfg.ui_host
    port = port or store.cfg.ui_port
    # Localhost-only by default: refuse non-loopback unless explicitly 127.0.0.1/localhost
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("UI must bind to localhost (127.0.0.1). Refusing host=" + host)
    app = ActivityASGI(build_app(store), store.root)
    url = f"http://{host}:{port}"
    print(json.dumps({"ok": True, "url": url, "root": str(root)}))
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="info")

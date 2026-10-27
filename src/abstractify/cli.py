from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from abstractify import __version__
from abstractify.config import EMBED_MODES
from abstractify.gitutil import git_changed_files
from abstractify.paths import find_project
from abstractify.project import init_project
from abstractify.size import GraphTooLarge
from abstractify.store import open_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="abstractify",
        description="Agent-written abstraction graphs over a project.",
    )
    parser.add_argument("--version", action="version", version=f"abstractify {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Install Abstractify into a project")
    p_init.add_argument("path", nargs="?", default=".", help="Project root (default: cwd)")
    p_init.add_argument("--embed-mode", choices=EMBED_MODES, default="none")
    p_init.add_argument("--embed-url", default="", help="REST endpoint for --embed-mode rest")
    p_init.add_argument("--embed-model", default="", help="Local model name override")
    p_init.add_argument("--custom-adapter", default="", help="Python file for --embed-mode custom")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--example", action="store_true", help="Seed a tiny example graph")
    p_init.add_argument(
        "--download-model",
        action="store_true",
        help="For local mode, download the ~2GB model now",
    )
    p_init.set_defaults(func=_cmd_init)

    p_serve = sub.add_parser("serve", help="Run the MCP server")
    p_serve.add_argument("path", nargs="?", default=".")
    p_serve.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=0)
    p_serve.set_defaults(func=_cmd_serve)

    p_ui = sub.add_parser("ui", help="Run the live localhost web UI")
    p_ui.add_argument("path", nargs="?", default=".")
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=0)
    p_ui.add_argument("--open", action="store_true")
    p_ui.set_defaults(func=_cmd_ui)

    p_aff = sub.add_parser(
        "affected",
        help="After an edit: list entities/graphs linked to changed files (no auto-mutate)",
    )
    p_aff.add_argument("files", nargs="*")
    p_aff.add_argument("--git", action="store_true", help="Use files git reports as changed")
    p_aff.add_argument("--path", default=".", help="Project root")
    p_aff.set_defaults(func=_cmd_affected)

    p_search = sub.add_parser("search", help="Search entities (text + semantic)")
    p_search.add_argument("query")
    p_search.add_argument("--path", default=".")
    p_search.add_argument("-k", type=int, default=20)
    p_search.set_defaults(func=_cmd_search)

    p_path = sub.add_parser("path", help="How two abstractions are connected")
    p_path.add_argument("source")
    p_path.add_argument("target")
    p_path.add_argument("--graph")
    p_path.add_argument("--directed", action="store_true")
    p_path.add_argument("--path", dest="root", default=".")
    p_path.set_defaults(func=_cmd_path)

    p_ex = sub.add_parser("explain", help="Explain one abstraction")
    p_ex.add_argument("entity")
    p_ex.add_argument("--path", default=".")
    p_ex.set_defaults(func=_cmd_explain)

    p_graph = sub.add_parser("graph", help="Create/update/delete/list graphs")
    g_sub = p_graph.add_subparsers(dest="gcmd", required=True)
    g_list = g_sub.add_parser("list")
    g_list.add_argument("--kind", choices=("structural", "flow"))
    g_list.add_argument("--path", default=".")
    g_list.set_defaults(func=_cmd_graph_list)
    g_get = g_sub.add_parser("get")
    g_get.add_argument("id")
    g_get.add_argument("--path", default=".")
    g_get.set_defaults(func=_cmd_graph_get)
    g_create = g_sub.add_parser("create")
    g_create.add_argument("--name", required=True)
    g_create.add_argument("--kind", required=True, choices=("structural", "flow"))
    g_create.add_argument("--principle", required=True)
    g_create.add_argument("--description", default="")
    g_create.add_argument("--from-json", dest="from_json")
    g_create.add_argument("--confirm-large", action="store_true")
    g_create.add_argument("--path", default=".")
    g_create.set_defaults(func=_cmd_graph_create)
    g_update = g_sub.add_parser("update")
    g_update.add_argument("id")
    g_update.add_argument("--name")
    g_update.add_argument("--kind", choices=("structural", "flow"))
    g_update.add_argument("--principle")
    g_update.add_argument("--description")
    g_update.add_argument("--from-json", dest="from_json")
    g_update.add_argument("--confirm-large", action="store_true")
    g_update.add_argument("--path", default=".")
    g_update.set_defaults(func=_cmd_graph_update)
    g_del = g_sub.add_parser("delete")
    g_del.add_argument("id")
    g_del.add_argument("--path", default=".")
    g_del.set_defaults(func=_cmd_graph_delete)

    p_ent = sub.add_parser("entity", help="Targeted entity edits")
    e_sub = p_ent.add_subparsers(dest="ecmd", required=True)
    e_list = e_sub.add_parser("list")
    e_list.add_argument("--query")
    e_list.add_argument("--graph")
    e_list.add_argument("--path", default=".")
    e_list.set_defaults(func=_cmd_entity_list)
    e_up = e_sub.add_parser("upsert")
    e_up.add_argument("--name", required=True)
    e_up.add_argument("--description", default="")
    e_up.add_argument("--graph")
    e_up.add_argument("--id")
    e_up.add_argument("--code-ref", action="append", default=[], help="path[:start[:end]]")
    e_up.add_argument("--path", default=".")
    e_up.set_defaults(func=_cmd_entity_upsert)

    p_snap = sub.add_parser("snapshot", help="Snapshot a graph")
    s_sub = p_snap.add_subparsers(dest="scmd", required=True)
    s_c = s_sub.add_parser("create")
    s_c.add_argument("graph_id")
    s_c.add_argument("--label", default="")
    s_c.add_argument("--path", default=".")
    s_c.set_defaults(func=_cmd_snap_create)
    s_l = s_sub.add_parser("list")
    s_l.add_argument("--graph")
    s_l.add_argument("--path", default=".")
    s_l.set_defaults(func=_cmd_snap_list)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GraphTooLarge as exc:
        _print(exc.as_dict())
        return 2
    except (FileNotFoundError, FileExistsError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _root(path: str) -> Path:
    p = Path(path).resolve()
    try:
        return find_project(p)
    except FileNotFoundError:
        if (p / ".abstractify" / "config.toml").is_file():
            return p
        raise


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    cfg = init_project(
        root,
        embed_mode=args.embed_mode,
        embed_url=args.embed_url,
        embed_model=args.embed_model or None,
        custom_adapter=args.custom_adapter,
        force=args.force,
        example=args.example,
        download_model_now=args.download_model,
    )
    _print(
        {
            "ok": True,
            "root": str(root),
            "embed_mode": cfg.embed_mode,
            "ui": f"abstractify ui  → http://{cfg.ui_host}:{cfg.ui_port}",
            "serve": "abstractify serve  (MCP stdio)",
        }
    )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from abstractify.mcp_server import run_mcp

    root = _root(args.path)
    run_mcp(root, transport=args.transport, host=args.host, port=args.port or None)
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    from abstractify.ui_server import run_ui

    root = _root(args.path)
    run_ui(root, host=args.host, port=args.port or None, open_browser=args.open)
    return 0


def _cmd_affected(args: argparse.Namespace) -> int:
    root = _root(args.path)
    files = list(args.files)
    if args.git:
        files.extend(git_changed_files(root))
    if not files:
        print("No files given. Pass paths or --git.", file=sys.stderr)
        return 1
    store = open_store(root)
    try:
        _print(store.affected_by_files(files))
    finally:
        store.close()
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.search(args.query, k=args.k))
    finally:
        store.close()
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    store = open_store(_root(args.root))
    try:
        _print(
            store.shortest_path(
                args.source, args.target, graph_id=args.graph, undirected=not args.directed
            )
        )
    finally:
        store.close()
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.explain(args.entity))
    finally:
        store.close()
    return 0


def _cmd_graph_list(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.list_graphs(kind=args.kind))
    finally:
        store.close()
    return 0


def _cmd_graph_get(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        graph = store.get_graph(args.id)
        if graph is None:
            print("graph not found", file=sys.stderr)
            return 1
        _print(graph)
    finally:
        store.close()
    return 0


def _load_json_doc(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cmd_graph_create(args: argparse.Namespace) -> int:
    extra = _load_json_doc(args.from_json)
    store = open_store(_root(args.path))
    try:
        graph = store.create_graph(
            name=args.name,
            kind=args.kind,
            principle=args.principle,
            description=args.description,
            entities=extra.get("entities"),
            edges=extra.get("edges"),
            confirm_large=args.confirm_large,
        )
        _print(graph)
    finally:
        store.close()
    return 0


def _cmd_graph_update(args: argparse.Namespace) -> int:
    extra = _load_json_doc(args.from_json)
    store = open_store(_root(args.path))
    try:
        graph = store.update_graph(
            args.id,
            name=args.name,
            kind=args.kind,
            principle=args.principle,
            description=args.description,
            entities=extra.get("entities"),
            edges=extra.get("edges"),
            confirm_large=args.confirm_large,
        )
        _print(graph)
    finally:
        store.close()
    return 0


def _cmd_graph_delete(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        ok = store.delete_graph(args.id)
        _print({"ok": ok})
        return 0 if ok else 1
    finally:
        store.close()


def _parse_code_ref(spec: str) -> dict:
    parts = spec.split(":")
    path = parts[0]
    start = int(parts[1]) if len(parts) > 1 and parts[1] else None
    end = int(parts[2]) if len(parts) > 2 and parts[2] else None
    return {"path": path, "start_line": start, "end_line": end}


def _cmd_entity_upsert(args: argparse.Namespace) -> int:
    spec = {
        "id": args.id,
        "name": args.name,
        "description": args.description,
        "code_refs": [_parse_code_ref(s) for s in args.code_ref],
    }
    if not spec["id"]:
        spec.pop("id")
    store = open_store(_root(args.path))
    try:
        _print(store.upsert_entity(spec, graph_id=args.graph))
    finally:
        store.close()
    return 0


def _cmd_entity_list(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.list_entities(query=args.query, graph_id=args.graph))
    finally:
        store.close()
    return 0


def _cmd_snap_create(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.create_snapshot(args.graph_id, label=args.label))
    finally:
        store.close()
    return 0


def _cmd_snap_list(args: argparse.Namespace) -> int:
    store = open_store(_root(args.path))
    try:
        _print(store.list_snapshots(graph_id=args.graph))
    finally:
        store.close()
    return 0

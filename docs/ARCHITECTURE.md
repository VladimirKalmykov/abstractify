# Abstractify architecture

Onboarding for someone who will change the Python package, MCP tools, or localhost UI. Product intent lives in [concept.md](concept.md); this file describes how the prototype is wired.

## What it is

Abstractify stores **agent-written abstraction graphs** next to a project. Vertices are named entities with short descriptions and optional code grounding (file + line range). Graphs are **structural** or **flow**. SQLite is the live source of truth. A JSON file per graph is a companion dump only.

Install this repo, then init inside a target project:

```bash
pip install -e '.[dev]'
abstractify init --embed-mode none --example
abstractify ui          # http://127.0.0.1:8765  (localhost only)
abstractify serve       # MCP, stdio
abstractify affected --git
```

Cursor MCP config (stdio):

```json
{
  "mcpServers": {
    "abstractify": {
      "command": "abstractify",
      "args": ["serve", "/absolute/path/to/project"]
    }
  }
}
```

HTTP MCP: `abstractify serve --transport http` on `127.0.0.1:8766`, endpoint `/mcp`.

## Layout

```
.
  pyproject.toml
  src/abstractify/
    cli.py              # init / serve / ui / affected / graph / entity / search / path / explain / snapshot
    store.py            # SQLite mutations + queries
    schema.sql
    mcp_server.py       # MCP 2 MCPServer tools
    ui_server.py        # Starlette API + static UI
    config.py           # .abstractify/config.toml
    project.py          # init + skill install
    embeddings/         # none | local | rest | custom
    skills/             # SKILL.md copied into .cursor/skills/abstractify
    ui/                 # React + D3/SVG (Vite); dist shipped with the package
  tests/
  docs/ARCHITECTURE.md
  docs/concept.md
```

On-disk project tree after `init`:

```
.abstractify/
  config.toml
  abstractify.db          # live source of truth (WAL)
  graphs/<id>.json        # dump after each write
  snapshots/<id>.json
.cursor/skills/abstractify/SKILL.md
AGENTS.md                 # marked always-on block
```

## Runtime

Three processes can share one DB (WAL):

1. **CLI** — argparse, JSON on stdout. `init` / `serve` / `ui` are the named product commands. `affected` is the post-edit skill command. `graph` / `entity` / `search` / `path` / `explain` / `snapshot` exist so a human or agent can work without MCP.
2. **MCP** (`mcp.server.mcpserver.MCPServer`) — read **and** write tools. Tools call `Store`; they never open the JSON files.
3. **UI** — Starlette on `127.0.0.1:8765`. `/api/*` hits `Store`. The React chrome is served from `ui/dist`. Non-loopback hosts are refused.

`open_store(root)` loads config, builds an embedder, opens SQLite.

## Schema (SQLite)

- `graphs` — `kind` is `structural` | `flow`; `principle` is the user-defined abstraction principle.
- `entities` — global registry (an entity can sit in several graphs).
- `graph_entities` — membership.
- `edges` — typed `relation` (`knows_about`, `does_not_know_about`, `calls`, `responds_to`, or any string until the vocabulary closes). `kind` is `structural` | `flow` | `meta`.
- `meta_links` — extra-graph relationships between entities.
- `code_refs` — file path + optional line range. Reverse index is a path/range query over this table.
- `snapshots` — JSON payload of one graph at a point in time.
- `entity_embeddings` — JSON float vectors. sqlite-vec `vec_entities` is created lazily when a dimension is known; cosine over `entity_embeddings` is the fallback (graphs are meant to stay small).

## Graph create/update

`Store.create_graph` / `update_graph` accept optional `entities` and `edges` arrays (bulk). Targeted tools (`upsert_entity`, `upsert_edge`, `add_meta_link`) patch one object. Every successful write refreshes `.abstractify/graphs/<id>.json`.

Size guard (`size.py`): refuse above `max_entities_per_graph` (80) or `max_edges_per_graph` (200) unless `confirm_large=true`. Hard refuse above `hard_max_entities` (500). Config is overridable in `config.toml`.

## Embeddings (chosen at `init`)

| Mode | Class | Notes |
|---|---|---|
| `none` | `NoneEmbedder` | substring + IDF; no vectors |
| `local` | `LocalEmbedder` | FastEmbed (LocalEmbeddingService-style), default `intfloat/multilingual-e5-large`, shared cache `%LOCALAPPDATA%/abstractify/models` (Windows), `~/Library/Caches/abstractify/models` (macOS), or `~/.cache/abstractify/models` (Linux); override `ABSTRACTIFY_EMBED_MODEL_CACHE`; `pip install 'abstractify[local]'`; `--download-model` |
| `rest` | `RestEmbedder` | `POST {"texts":[...], "input_type": "document"|"query"}`; compatible with LocalEmbeddingService (`vectors` in response). Default URL `http://127.0.0.1:7342/v1/embeddings`. API key from `ABSTRACTIFY_EMBED_API_KEY` if needed. |
| `custom` | `CustomEmbedder` | user Python file with `embed(texts)` and optional `retrieve` — see `embeddings/adapter_example.py` |

Search always runs IDF; vector/custom retrieve is merged in when the mode is not `none`.

## Post-edit skill

Not a watcher. After the agent **finishes** an edit it runs `abstractify affected --git` (or `affected_by_files` MCP). Abstractify returns linked entities and graphs. The skill text says **verify, do not auto-mutate**.

## UI

React (forms, left rail, Graphs/Entities tabs, structural/flow filter, entity search + create). D3 force-directed layout with **SVG** nodes/edges (not Canvas/WebGL). Dark neon, dotted canvas, thin dark-cyan card outlines. Each vertex card shows three bottom counts: filesystem refs, entity degree, meta-links.

Rebuild the UI:

```bash
cd src/abstractify/ui
npm install
npm run build
```

`abstractify ui` serves that `dist/` plus `/api`.

## Tests

```bash
pip install -e '.[dev]'
pytest tests
```

Core coverage: init, graph create/update, JSON dump vs SQLite truth, reverse index, affected, size guard, snapshots, custom embedder, MCP tool names, UI HTTP API.

## What is real vs scaffolded

**Real:** package + CLI, SQLite schema, graph create/update/delete, targeted entity/edge edits, meta-links, reverse index, search (IDF + vector path), path/explain, snapshots, size guard, four embedder implementations, MCP write/read tools, skill install, live localhost UI (React + D3/SVG), JSON companion files.

**Thin on purpose:** local model is not downloaded in tests (~2 GB); REST is a client without a bundled server; sqlite-vec is used when it loads and otherwise cosine-fallback; edge vocabulary is typed but not closed; UI is a viewer/creator, not a full graph editor.

# Abstractify — concept

Running record of the product concept. Implementation notes are appended when a decision is settled in code; earlier sections are not rewritten away.

Abstractify helps people **understand a project through simple views at different abstraction slices**. It is not a giant interconnected code graph.

Vertices are **abstractions / entities** chosen by a human via an AI agent. They sit **above** implementation but stay **grounded** in it (modules and optional line ranges). There are **many graphs** in a registry, of at least two kinds: **structural** and **flow**.

Abstraction cannot be automated. Only the agent can decide what to abstract and how, so **write access is essential**.

---

## Why not Graphify

Graphify (research: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)) turns a repo into a derived `graphify-out/graph.json`. Local MCP is **read-only**. Writes happen by rebuilding that JSON (`graphify update .`). `graphify serve` is MCP only; `graph.html` is a static export.

Abstractify inverts that:

| | Graphify | Abstractify |
|---|---|---|
| What the graph is | Code/docs knowledge graph | User-defined **abstractions** over the project |
| Who decides nodes | Extractors | **Only the agent** (on behalf of the user) |
| Local MCP | Read-only | **Read and write** |
| Writes | Rebuild `graph.json` from source | Agent mutates graphs/entities/edges/metadata in place |
| UI | Static `graph.html` | **Mandatory live localhost UI** on the same backend |
| Serve | MCP-only | Separate `serve` (MCP) and `ui` (live web) |
| Search | Substring + IDF over labels | Text + optional **vector** search over entity descriptions |
| After a code change | Incremental AST rebuild | Return linked abstractions; **agent verifies**; **no auto-mutate** |

Do not copy Graphify’s AST extractors, Leiden communities, god-nodes, wiki export, `save-result` memory loop, or PR tools.

---

## Package and CLI

One Python package named `abstractify`, with three named subcommands:

- `abstractify init` — install into a project
- `abstractify serve` — MCP server
- `abstractify ui` — live web interface on localhost

The UI is not a static file. It is a live server that reads the **same SQLite backend** as the CLI, so the graph is always up to date. The MCP server uses that backend too, rather than reading JSON from disk.

SQLite (with sqlite-vec) lives **inside the project**. No external database server.

Install chooses an **embedding mode** (see below).

---

## Storage

- **Live source of truth** for CLI, MCP, and UI: **SQLite** (sqlite-vec for vectors when embeddings are on).
- **JSON on disk** remains as a Graphify-like companion artifact (export of each graph). Tools and UI must not treat JSON as the live source of truth.
- Embeddings (when enabled) are of **entity short descriptions**.
- No Neo4j, no hosted DB.

---

## Graph model

### Many graphs, two kinds

A registry of graphs. Each graph is **structural** or **flow**. The UI can show all, or filter to one kind.

### Vertices = abstractions / entities

An entity has:

- name
- short description (stored; also embedded when embeddings are on)
- metadata pointing at real code: modules / locations; optionally specific lines or line ranges
- links to other entities
- meta-links (relationships)

One abstraction can span several modules. Example: abstraction “image preparation” (resize, JPEG compression, crop) may link to functions living in different places. Example with lines: abstraction “code generation for sending” → `validation_code_maker.ts`, lines X–Y.

Abstraction sits above implementation but stays grounded in it.

Vertex types and color semantics are **not enumerated** yet. A single color for now.

### Edges

Structural graph edge types can express whether services know about each other — e.g. **knows about** vs **does not know about**. Other candidates: **calls**, **responds to**. Exact set still open; implement as **typed edges** with that candidate vocabulary, and allow additional relation strings until the set is closed.

### Meta-links

Agent-writable relationships on an entity, distinct from ordinary graph edges (may be cross-graph). Adding meta-links is a first-class MCP operation.

### Reverse index: file → abstractions

Required. From file (and line range) to **every abstraction that references it**. Search is across all graphs / the registry. When a module changes, every possibly affected abstraction can be found.

### Abstraction principle

The principle is **not fixed**. The user defines it when asking the AI to form abstractions, and it is **recorded together with the graph**.

Examples only (not the principle itself):

1. «создай абстракцию по межсетевым соединениям во всём проекте» — entities grouped by how they are connected via the network.
2. «абстрагируй проект по использованию языков программирования» — the project split into parts written in different languages.

Any such principle is valid. Do not hard-code network topology or language-split as built-in graph types.

### Size

Purpose is simple views at different abstraction slices, not giant graphs. If a graph would be too large, the agent should **ask for additional confirmation** before creating it, **or refuse**.

### Snapshots

Graphs are versioned over time because agents write them.

---

## MCP

Abstractify has its own MCP server. The agent **must mutate** the graph.

Intended behavior (tool names are an implementation detail, recorded later):

**Write**

1. Create graph
2. Update graph
3. Delete graph
4. Targeted changes to a specific edge
5. Targeted changes to a specific entity
6. Add meta-links (relationships) for an entity
7. Snapshots

**Read**

8. File-based lookup (reverse index)
9. Search: text by entity names; semantic over descriptions when embeddings are on; substring/IDF fallback when not
10. Path and explain (how two abstractions are connected; explain one concept)

Listing graphs and entities is required by the UI and by the post-edit skill.

Do not add Graphify-only tools (`god_nodes`, `get_community`, `list_prs`, `remember`, …).

---

## Auto-rebuild skill

After the agent **finishes a specific edit** (not during it):

1. The skill runs an Abstractify command, passing the list of changed files — or files git reports as changed.
2. Abstractify uses the reverse index and **returns** the entities and graphs connected to those files.
3. The agent **reads** those graphs and entities and **verifies** whether anything should change.
4. The agent **does not auto-mutate**. If something should change, it uses the write MCP tools.

---

## Four embedding modes (chosen at install)

1. **Local model** — downloaded automatically at install, roughly **~2 GB**.
2. **External REST API** — external embedding model via API and endpoint.
3. **No embeddings** — for weak computers and no API. Search is substring/IDF. No extra compute, no external API.
4. **Fully custom** — user points Abstractify at their own already-running embedding service (avoids a second 2 GB download). Small adapter: create embeddings on write, retrieve embeddings.

Modes 1, 2, and 4 feed sqlite-vec for semantic search over entity descriptions.

---

## UI

Mandatory. Localhost. All graphs and flows are viewed visually.

**Layout**

- Left side: list of graphs.
- Side control panel with tabs:
  - **Graphs** — all types, or filter structural only / flow only.
  - **Entities** — all entities as a list with search. Creating an entity: name + short description. Descriptions go to the vector DB when embeddings are on.

**Aesthetic**

Dark, futuristic neon.

- Canvas background: evenly spaced dots.
- Zoom in/out.
- Abstractions: thin neon outlines, dark cyan.
- Single color for now; color may later differentiate vertex and edge types.

**Vertex cards**

- Small cards showing the entity name.
- Counts at the bottom as small text, laid out horizontally: `icon + value`, `icon + value`, `icon + value`.
- Named counts: (1) filesystem links, (2) links to other entities.
- Third count was left open in discussion.

**Layout algorithm**

Automatic placement from relationships. For now: force-directed (Graphify-style).

## UI technology

The UI is built with React for forms and interface elements, and the graph visualization uses D3.js with SVG rendering (not Canvas or WebGL for now). Start with SVG since it handles hundreds to thousands of nodes well; Canvas or WebGL can be considered later if performance becomes an issue. D3 provides the force-directed layout (Graphify-style) and interaction math, while SVG renders the nodes and edges as DOM elements.

Live server, same SQLite backend as CLI/MCP — not a static HTML export.

---

## Agent-driven mutation

1. Abstraction is not automated. Write access is essential.
2. The agent mutates via MCP (and CLI equivalents): graphs, entities, edges, metadata, meta-links, snapshots.
3. After code edits, Abstractify does not rewrite the graph. It returns affected entities/graphs; the agent verifies.
4. User-defined principle is stored on the graph.
5. Size guard: confirm or refuse oversized graphs.
6. UI so humans can see graphs/flows (and create entities from the Entities tab).

---

## Implementation notes (prototype)

Settled while building the first prototype. Earlier sections stay as the discussion record.

- **Project directory:** `.abstractify/` in the project root. Database: `.abstractify/abstractify.db`. Config: `.abstractify/config.toml`. Graph JSON companions: `.abstractify/graphs/<id>.json` (written after mutations; never the live source).
- **JSON sync:** SQLite is source of truth. JSON is a dump after each successful write (and on snapshot). MCP/UI/CLI never read JSON for live queries.
- **Ports:** UI binds `127.0.0.1:8765`. MCP stdio by default; `--transport http` on `127.0.0.1:8766`.
- **Size thresholds** (config, overridable): warn/refuse above **80 entities** or **200 edges** in one graph unless `confirm_large=true`. Hard refuse above **500 entities** even with confirm.
- **Edge vocabulary:** stored as typed relation strings. Built-in labels: `knows_about`, `does_not_know_about`, `calls`, `responds_to`. Other strings allowed until the set is closed.
- **Meta-links:** separate `meta_links` table (entity ↔ entity + relation + note), not graph-scoped edges. Vertex-card **third count** = meta-link count (discussion left this slot open).
- **Snapshots:** SQLite `snapshots` rows (JSON payload of one graph) plus `.abstractify/snapshots/<id>.json`.
- **Post-edit command:** `abstractify affected [--git] [FILE ...]`. Same behavior as MCP `affected_by_files`.
- **Skill install:** `init` writes `.cursor/skills/abstractify/SKILL.md` and a marked block in `AGENTS.md` (created if missing).
- **Local embedding model:** FastEmbed, default `intfloat/multilingual-e5-large` (1024-d). Weights are cached once per machine: `%LOCALAPPDATA%\abstractify\models` on Windows, `~/Library/Caches/abstractify/models` on macOS, `$XDG_CACHE_HOME/abstractify/models` or `~/.cache/abstractify/models` on Linux (override with `ABSTRACTIFY_EMBED_MODEL_CACHE`). Lazy-loaded on first embed or `init --download-model`. Uses `query:` / `passage:` prefixes like LocalEmbeddingService. Not downloaded during ordinary tests.
- **Custom adapter:** a Python file with `embed(texts: list[str]) -> list[list[float]]` and optional `retrieve(query, items, k)`.
- **REST embedder:** `POST` JSON `{"texts": [...]}` to the configured URL; accepts `{"embeddings": [[...]]}` or OpenAI-style `{"data": [{"embedding": [...]}]}`. API key from `ABSTRACTIFY_EMBED_API_KEY` (not argv).
- **UI writes:** Entities tab can create entities; Graphs tab can create a graph (name, kind, principle). Agent MCP remains the primary mutation path.
- **Distribution:** installable Python package (`pip install -e ./abstractify`). No standalone binary in this pass.

---
name: abstractify
description: >-
  Use Abstractify through its CLI and MCP server before reading source code.
  Covers every abstractify command, starting MCP with abstractify start, and
  the hard rules that abstractions precede graphs and the database is never
  edited directly. After a task that changes files, look up the linked
  abstractions and correct them; ask before deleting one.
---

# Abstractify

Abstractify is the required interface for reading and writing this project's abstractions. MCP is how the agent performs those operations. The CLI is the same tool from the shell. There is no `stop` command.

## Hard rules

- **Abstractions are created first; graphs are created from abstractions.** Before creating a graph, the agent must understand which abstraction the graph represents.
- **Whenever trying to understand how a module, system, or connections work, always first try to find an existing graph for it in Abstractify before reading source code directly.**
- **If the MCP server is not working, you must run `abstractify start`.** If `abstractify status` shows the service is not running (disconnected), you **must** run `abstractify start` yourself. You **must not** bypass it by writing directly to the database with a Python script or any other direct method.
- **Direct editing of the database is completely forbidden.** Never touch the database manually, including the database folder and files. No Python scripts, no manual writes, no workarounds.
- **After every task that changes files, look up the linked abstractions and correct them.** When the task is finished, search Abstractify by those files (`affected` / `affected_by_files`, or `lookup_by_file`). Check each hit against the new abstract scheme and against the code as it is now. If an abstraction no longer matches, edit it through MCP. If the correction is to delete an abstraction, ask the user for permission first. Do not delete it on your own.

## MCP server

`abstractify start` runs the HTTP MCP server and the localhost UI together. That is the required way to bring the interface up when it is down. The process stops on its own after an idle timeout (default 3600 seconds) unless started with `--always-on`; otherwise it stops on SIGINT or SIGTERM. There is no `stop` subcommand.

`abstractify serve` is the MCP server alone: stdio by default, or HTTP with `--transport http`. Agents use the MCP tools, not the SQLite files.

The server reads and writes the same SQLite store as the CLI. It provides:

- Graphs: `list_graphs`, `get_graph`, `create_graph`, `update_graph`, `delete_graph`
- Entities: `list_entities`, `get_entity`, `upsert_entity`, `delete_entity`
- Edges: `upsert_edge`, `delete_edge`
- Meta-links: `add_meta_link`, `delete_meta_link`
- Lookup: `lookup_by_file`, `affected_by_files`, `search`, `path`, `explain`
- Snapshots: `create_snapshot`, `list_snapshots`, `get_snapshot`, `restore_snapshot`

Create an abstraction (entity) before the graph that contains it. Record the user-defined principle on the graph. If a write is refused because the graph is too large, ask the user before retrying with `confirm_large=true`.

## CLI commands

Top-level help lists: `version` (`v`), `init`, `serve`, `ui`, `start`, `status`, `embeddings`, `affected`, `search`, `path`, `explain`, `graph`, `entity`, `snapshot`. `--version` prints `abstractify` plus the version. `version` and `v` print only the version number and do not open the database.

| Command | What it does |
|---|---|
| `version`, `v` | Print the package version. |
| `init` | Install Abstractify into a project. |
| `serve` | Run the MCP server. |
| `ui` | Run the live localhost web UI. |
| `start` | Run MCP HTTP serve and the localhost UI together. |
| `status` | Check whether serve and UI are up. |
| `embeddings` | Enable or backfill embeddings on an existing project (no re-init). |
| `embeddings enable` | Set `embed_mode` in config.toml (local FastEmbed or REST). |
| `embeddings backfill` | Embed entities missing vectors. |
| `affected` | After an edit: list entities and graphs linked to changed files. It does not change the graph. |
| `search` | Search entities (text, plus semantic search when embeddings are on). |
| `path` | Show how two abstractions are connected. |
| `explain` | Explain one abstraction. |
| `graph` | Create, update, delete, or list graphs. |
| `graph list` | List graphs. Optional `--kind structural` or `flow`. |
| `graph get` | Get one graph. |
| `graph create` | Create a graph. Requires `--name`, `--kind`, and `--principle`. |
| `graph update` | Update a graph. |
| `graph delete` | Delete a graph. |
| `entity` | Targeted entity edits. |
| `entity list` | List entities. |
| `entity upsert` | Create or update one entity, including code refs and metadata. |
| `snapshot` | Snapshot a graph. |
| `snapshot create` | Store a snapshot of one graph. |
| `snapshot list` | List snapshots. |

---
name: abstractify
description: After finishing a code edit, look up Abstractify abstractions tied to changed files and verify graphs. Use when the repo has a .abstractify/ directory.
---

# Abstractify skill

Abstraction is **not** automated. You decide what to abstract and how. Abstractify stores those decisions as graphs of entities grounded in real files.

## After you finish an edit (not during)

1. Run:

```bash
abstractify affected --git
```

Or pass files explicitly:

```bash
abstractify affected path/to/changed.py another.ts
```

2. Abstractify returns the **entities and graphs** linked to those files via the reverse index. It does **not** rewrite the graph.
3. Read those entities/graphs (`get_entity`, `get_graph`, `explain`). Verify whether names, descriptions, code refs, or edges still match the code.
4. Only then mutate, using write tools (`update_graph`, `upsert_entity`, `upsert_edge`, …). If nothing should change, stop.

## Reading

- `search` — text by name; semantic over descriptions when embeddings are on.
- `lookup_by_file` — entering a module, see which abstractions depend on it.
- `path` / `explain` — how two abstractions connect; one concept plus neighbors.
- `list_graphs` / `list_entities`

## Writing

- Create a graph with the **user-defined principle** stored on it. Do not invent a fixed principle (network topology and language-split are examples only).
- Prefer targeted entity/edge edits over replacing a whole graph.
- If create/update is refused as too large: ask the user, then retry with `confirm_large=true`, or refuse.

## UI

`abstractify ui` is a live localhost viewer on the same SQLite backend.

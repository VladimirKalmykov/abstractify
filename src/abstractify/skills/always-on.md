## Abstractify

**What it is.** Abstractify is a project-local map of **abstractions** (named concepts, responsibilities, flows) linked to real code via graphs and file refs. It is built for **humans and agents alike**: you use the same CLI and MCP tools to read and maintain that map while developing the product. **Search** finds abstractions by topic or name; **path** shows how two concepts connect through the graph; **explain** expands one abstraction with neighbors and grounding. Prefer this layer when you need *why* and *how pieces relate*, not only raw file text.

If `.abstractify/` exists in this repo:

- Do **not** run `abstractify init` yourself; project initialization is for humans/setup only.
- To turn on embeddings on an existing project (graphs unchanged), humans edit `.abstractify/config.toml` (`embed_mode = "local"` or `rest` with `embed_url = "http://127.0.0.1:7342/v1/embeddings"`) or run `abstractify embeddings enable --mode …`, then restart serve/UI. Missing entity vectors are backfilled on the next store open.
- If `abstractify status` shows the service is not running (disconnected), you **must** run `abstractify start` yourself.
- **Hard rule.** If the MCP server is not working, you **must** start it with `abstractify start`. You **must not** bypass it by writing directly to the database with a Python script or any other direct method.
- **Hard rule.** Direct editing of the database is completely forbidden. Never touch the database manually, including the database folder and files. No Python scripts, no manual writes, no workarounds.
- **Always work with Abstractify.** This is not optional and not a fallback: it is the main way you orient in this repo, before a broad grep, before drafting a plan, and while you touch code. CLI: `abstractify search`, `abstractify path`, `abstractify explain`; or the equivalent MCP tools when connected.
- **When you work on a topic**, run `abstractify search` on that topic first and read the hits. **When you open or change specific files**, use `abstractify path` / file-linked lookup (e.g. `lookup_by_file` via MCP) so you see which abstractions and graphs those paths belong to.
- **When you see a gap** (new module, boundary, or flow that others will need again), **propose** adding or updating abstractions in Abstractify — new entities, edges, or a small graph with a clear user-defined principle. Abstraction is not automated: only you decide what to record; ask the user when scope or graph size is unclear.
- After you **finish** a specific edit (not during it), run `abstractify affected --git` (or pass the changed file paths). Read the returned entities and graphs and **verify** whether they still match the code. Do **not** auto-mutate. If a graph or entity should change, use the write MCP tools with human/agent judgment.
- Abstraction is not automated: only you (the agent) decide what to abstract and how. Record the user-defined principle on each graph.
- If a graph would be large, ask the user to confirm or refuse. Abstractify's job is simple views at different abstraction slices.

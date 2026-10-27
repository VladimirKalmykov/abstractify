## Abstractify

If `.abstractify/` exists in this repo:

- On a question about how the project is structured at an abstract level, use Abstractify (`abstractify search`, `abstractify path`, `abstractify explain`, or the MCP tools) before grepping blindly.
- After you **finish** a specific edit (not during it), run `abstractify affected --git` (or pass the changed file paths). Read the returned entities and graphs and **verify** whether they still match the code. Do **not** auto-mutate. If a graph or entity should change, use the write MCP tools with human/agent judgment.
- Abstraction is not automated: only you (the agent) decide what to abstract and how. Record the user-defined principle on each graph.
- If a graph would be large, ask the user to confirm or refuse. Abstractify's job is simple views at different abstraction slices.

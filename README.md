# Abstractify

Agent-written **abstraction graphs** over a project: SQLite source of truth, MCP read/write, and a live localhost UI.

```bash
pip install -e '.[dev]'
abstractify init --embed-mode none --example
abstractify ui          # http://127.0.0.1:8765
abstractify serve       # MCP stdio
abstractify affected --git
```

- Concept: [docs/concept.md](docs/concept.md)
- Onboarding / architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

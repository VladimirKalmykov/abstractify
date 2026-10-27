PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graphs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('structural', 'flow')),
  principle TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  metadata JSON NOT NULL DEFAULT '{}' CHECK (json_valid(metadata)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entities (
  graph_id TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  PRIMARY KEY (graph_id, entity_id)
);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  graph_id TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('structural', 'flow', 'meta')),
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_links (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  related_entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS code_refs (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  -- NULL/NULL: the whole module. start_line only: one line. both: a line range.
  start_line INTEGER,
  end_line INTEGER,
  note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_code_refs_path ON code_refs(path);
CREATE INDEX IF NOT EXISTS idx_edges_graph ON edges(graph_id);
CREATE INDEX IF NOT EXISTS idx_graph_entities_entity ON graph_entities(entity_id);

CREATE TABLE IF NOT EXISTS snapshots (
  id TEXT PRIMARY KEY,
  graph_id TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
  label TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_embeddings (
  entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  model TEXT NOT NULL
);

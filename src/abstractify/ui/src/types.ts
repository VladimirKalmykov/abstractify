export type GraphKind = "structural" | "flow";

export type GraphSummary = {
  id: string;
  name: string;
  kind: GraphKind;
  principle: string;
  description: string;
  entity_count: number;
  edge_count: number;
};

export type CodeRef = {
  id: string;
  path: string;
  start_line: number | null;
  end_line: number | null;
  note: string;
};

export type MetaLink = {
  id: string;
  entity_id: string;
  related_entity_id: string;
  relation: string;
  note: string;
};

export type Entity = {
  id: string;
  name: string;
  description: string;
  code_refs: CodeRef[];
  meta_links: MetaLink[];
  graphs: { id: string; name: string; kind: GraphKind; principle: string }[];
  degree: number;
  code_ref_count: number;
  meta_link_count: number;
};

export type Edge = {
  id: string;
  graph_id: string;
  source_id: string;
  target_id: string;
  relation: string;
  kind: string;
};

export type GraphDetail = GraphSummary & {
  entities: Entity[];
  edges: Edge[];
};

import type { GraphDetail } from "./types";

/** Stable key for force-layout: changes only when nodes/edges structure changes. */
export function graphLayoutKey(graph: GraphDetail | null): string | null {
  if (!graph) return null;
  const entities = graph.entities
    .map(
      (e) =>
        `${e.id}\t${e.name}\t${e.code_ref_count}\t${e.degree}\t${e.meta_link_count}`,
    )
    .sort()
    .join("\n");
  const edges = graph.edges
    .map((e) => `${e.id}\t${e.source_id}\t${e.target_id}\t${e.relation}`)
    .sort()
    .join("\n");
  return `${graph.id}\n${entities}\n${edges}`;
}

export function graphDetailEqual(a: GraphDetail, b: GraphDetail): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

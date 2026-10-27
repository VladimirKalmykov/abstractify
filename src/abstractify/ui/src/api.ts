import type { Entity, GraphDetail, GraphKind, GraphSummary } from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; embed_mode: string }>("/api/health"),
  graphs: (kind?: GraphKind | "all") =>
    req<{ graphs: GraphSummary[] }>(
      kind && kind !== "all" ? `/api/graphs?kind=${kind}` : "/api/graphs",
    ),
  graph: (id: string) => req<GraphDetail>(`/api/graphs/${encodeURIComponent(id)}`),
  createGraph: (body: { name: string; kind: GraphKind; principle: string; description?: string }) =>
    req<GraphDetail>("/api/graphs", { method: "POST", body: JSON.stringify(body) }),
  entities: (q?: string) =>
    req<{ entities: Entity[] }>(q ? `/api/entities?q=${encodeURIComponent(q)}` : "/api/entities"),
  createEntity: (body: { name: string; description: string; graph_id?: string }) =>
    req<Entity>("/api/entities", { method: "POST", body: JSON.stringify(body) }),
};

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { EntitiesPanel } from "./components/EntitiesPanel";
import { GraphCanvas } from "./components/GraphCanvas";
import { Sidebar } from "./components/Sidebar";
import type { Entity, GraphDetail, GraphKind, GraphSummary } from "./types";
import styles from "./App.module.css";

type Tab = "graphs" | "entities";
type Filter = "all" | GraphKind;

export function App() {
  const [tab, setTab] = useState<Tab>("graphs");
  const [filter, setFilter] = useState<Filter>("all");
  const [graphs, setGraphs] = useState<GraphSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GraphDetail | null>(null);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entityQuery, setEntityQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadGraphs = useCallback(async () => {
    const data = await api.graphs(filter);
    setGraphs(data.graphs);
    setSelectedId((cur) => {
      if (cur && data.graphs.some((g) => g.id === cur)) return cur;
      return data.graphs[0]?.id ?? null;
    });
  }, [filter]);

  const loadEntities = useCallback(async () => {
    const data = await api.entities(entityQuery || undefined);
    setEntities(data.entities);
  }, [entityQuery]);

  useEffect(() => {
    loadGraphs().catch((e) => setError(String(e)));
    const t = setInterval(() => loadGraphs().catch(() => undefined), 2500);
    return () => clearInterval(t);
  }, [loadGraphs]);

  useEffect(() => {
    loadEntities().catch((e) => setError(String(e)));
  }, [loadEntities]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    api
      .graph(selectedId)
      .then(setDetail)
      .catch((e) => setError(String(e)));
    const t = setInterval(() => {
      api.graph(selectedId).then(setDetail).catch(() => undefined);
    }, 2500);
    return () => clearInterval(t);
  }, [selectedId]);

  return (
    <div className={styles.shell}>
      <aside className={styles.side}>
        <div className={styles.brand}>
          <span className={styles.logo}>Abstractify</span>
          <span className={styles.tag}>localhost</span>
        </div>
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === "graphs" ? styles.tabActive : ""}`}
            onClick={() => setTab("graphs")}
            type="button"
          >
            Graphs
          </button>
          <button
            className={`${styles.tab} ${tab === "entities" ? styles.tabActive : ""}`}
            onClick={() => setTab("entities")}
            type="button"
          >
            Entities
          </button>
        </div>
        <div className={styles.body}>
          {tab === "graphs" ? (
            <Sidebar
              graphs={graphs}
              selectedId={selectedId}
              filter={filter}
              onFilter={setFilter}
              onSelect={setSelectedId}
              onCreated={() => loadGraphs()}
              error={error}
            />
          ) : (
            <EntitiesPanel
              entities={entities}
              query={entityQuery}
              onQuery={setEntityQuery}
              graphs={graphs}
              onCreated={() => {
                loadEntities();
                loadGraphs();
              }}
            />
          )}
        </div>
      </aside>
      <main className={styles.canvasWrap}>
        <GraphCanvas graph={detail} />
        <div className={styles.hint}>scroll to zoom · drag the canvas · drag a card</div>
      </main>
    </div>
  );
}

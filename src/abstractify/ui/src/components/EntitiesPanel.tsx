import { useState } from "react";
import { api } from "../api";
import type { Entity, GraphSummary } from "../types";
import styles from "./EntitiesPanel.module.css";

type Props = {
  entities: Entity[];
  query: string;
  onQuery: (q: string) => void;
  graphs: GraphSummary[];
  onCreated: () => void;
};

export function EntitiesPanel({ entities, query, onQuery, graphs, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [graphId, setGraphId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.createEntity({
        name,
        description,
        graph_id: graphId || undefined,
      });
      setName("");
      setDescription("");
      onCreated();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <input
        className={styles.search}
        placeholder="Search entities"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      <div className={styles.list}>
        {entities.map((ent) => (
          <div key={ent.id} className={styles.card}>
            <div className={styles.name}>{ent.name}</div>
            {ent.description ? <div className={styles.desc}>{ent.description}</div> : null}
            <div className={styles.counts}>
              <span>⬡ {ent.code_ref_count}</span>
              <span>⛓ {ent.degree}</span>
              <span>✦ {ent.meta_link_count}</span>
            </div>
          </div>
        ))}
        {entities.length === 0 ? <div className={styles.desc}>No entities yet.</div> : null}
      </div>
      <form className={styles.form} onSubmit={create}>
        <h3>New entity</h3>
        <input required placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea
          required
          rows={3}
          placeholder="Short description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <select value={graphId} onChange={(e) => setGraphId(e.target.value)}>
          <option value="">(no graph membership)</option>
          {graphs.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        {err ? <div className={styles.err}>{err}</div> : null}
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </button>
      </form>
    </>
  );
}

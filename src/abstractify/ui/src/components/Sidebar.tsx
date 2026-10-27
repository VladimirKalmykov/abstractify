import { useState } from "react";
import { api } from "../api";
import type { GraphKind, GraphSummary } from "../types";
import styles from "./Sidebar.module.css";

type Filter = "all" | GraphKind;

type Props = {
  graphs: GraphSummary[];
  selectedId: string | null;
  filter: Filter;
  onFilter: (f: Filter) => void;
  onSelect: (id: string) => void;
  onCreated: () => void;
  error: string | null;
};

export function Sidebar({
  graphs,
  selectedId,
  filter,
  onFilter,
  onSelect,
  onCreated,
  error,
}: Props) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<GraphKind>("structural");
  const [principle, setPrinciple] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const g = await api.createGraph({ name, kind, principle });
      setName("");
      setPrinciple("");
      onCreated();
      onSelect(g.id);
    } catch (err) {
      setFormError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error ? <div className={styles.err}>{error}</div> : null}
      <div className={styles.filter}>
        {(["all", "structural", "flow"] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            className={`${styles.chip} ${filter === f ? styles.chipOn : ""}`}
            onClick={() => onFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      <div className={styles.list}>
        {graphs.map((g) => (
          <button
            key={g.id}
            type="button"
            className={`${styles.item} ${selectedId === g.id ? styles.itemOn : ""}`}
            onClick={() => onSelect(g.id)}
          >
            <span className={styles.name}>{g.name}</span>
            <div className={styles.meta}>
              <span>{g.kind}</span>
              <span>
                {g.entity_count} ent · {g.edge_count} edg
              </span>
            </div>
            {g.principle ? <div className={styles.principle}>{g.principle}</div> : null}
          </button>
        ))}
        {graphs.length === 0 ? (
          <div className={styles.principle}>No graphs yet. Create one, or run abstractify init --example.</div>
        ) : null}
      </div>
      <form className={styles.form} onSubmit={create}>
        <h3>New graph</h3>
        <input
          required
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select value={kind} onChange={(e) => setKind(e.target.value as GraphKind)}>
          <option value="structural">structural</option>
          <option value="flow">flow</option>
        </select>
        <textarea
          required
          rows={3}
          placeholder="User-defined abstraction principle"
          value={principle}
          onChange={(e) => setPrinciple(e.target.value)}
        />
        {formError ? <div className={styles.err}>{formError}</div> : null}
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </button>
      </form>
    </>
  );
}

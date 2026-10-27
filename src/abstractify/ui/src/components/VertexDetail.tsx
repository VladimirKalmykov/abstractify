import { useState } from "react";
import type { CodeRef, Entity, GraphDetail } from "../types";
import styles from "./VertexDetail.module.css";

type Props = {
  entity: Entity;
  graph: GraphDetail;
  onClose: () => void;
};

type RelationGroup = {
  relation: string;
  outgoing: string[];
  incoming: string[];
};

function labelRelation(relation: string): string {
  return relation.replaceAll("_", " ");
}

function fileName(path: string): string {
  const norm = path.replaceAll("\\", "/");
  const name = norm.slice(norm.lastIndexOf("/") + 1);
  return name || norm;
}

function projectRelativePath(path: string): string {
  return path.replaceAll("\\", "/").replace(/^\.\//, "");
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

function buildGraphRelationGroups(entityId: string, graph: GraphDetail): RelationGroup[] {
  const names = new Map(graph.entities.map((e) => [e.id, e.name]));
  const map = new Map<string, RelationGroup>();

  for (const edge of graph.edges) {
    if (edge.source_id === entityId) {
      const rel = edge.relation;
      const g = map.get(rel) ?? { relation: rel, outgoing: [], incoming: [] };
      const name = names.get(edge.target_id) ?? edge.target_id;
      if (!g.outgoing.includes(name)) g.outgoing.push(name);
      map.set(rel, g);
    }
    if (edge.target_id === entityId) {
      const rel = edge.relation;
      const g = map.get(rel) ?? { relation: rel, outgoing: [], incoming: [] };
      const name = names.get(edge.source_id) ?? edge.source_id;
      if (!g.incoming.includes(name)) g.incoming.push(name);
      map.set(rel, g);
    }
  }

  return [...map.values()].sort((a, b) => a.relation.localeCompare(b.relation));
}

function buildMetaGroups(entity: Entity, graph: GraphDetail): Map<string, string[]> {
  const names = new Map(graph.entities.map((e) => [e.id, e.name]));
  const map = new Map<string, string[]>();

  for (const ml of entity.meta_links) {
    const otherId =
      ml.entity_id === entity.id ? ml.related_entity_id : ml.entity_id;
    const name = names.get(otherId) ?? otherId;
    const list = map.get(ml.relation) ?? [];
    if (!list.includes(name)) list.push(name);
    map.set(ml.relation, list);
  }

  return map;
}

function FileEntry({ pathRef }: { pathRef: CodeRef }) {
  const relative = projectRelativePath(pathRef.path);
  const tipId = `file-path-${pathRef.id}`;
  const [tip, setTip] = useState<{ top: number; left: number } | null>(null);

  function place(target: HTMLElement) {
    const box = target.getBoundingClientRect();
    setTip({ top: box.top + box.height / 2, left: box.right + 10 });
  }

  return (
    <li
      className={styles.fileRow}
      onMouseEnter={(event) => place(event.currentTarget)}
      onMouseLeave={() => setTip(null)}
      onFocus={(event) => place(event.currentTarget)}
      onBlur={() => setTip(null)}
    >
      <span className={styles.fileName} aria-describedby={tipId}>
        {fileName(relative)}
      </span>
      {tip ? (
        <span
          id={tipId}
          className={styles.pathTip}
          role="tooltip"
          style={{ top: tip.top, left: tip.left }}
        >
          {relative}
        </span>
      ) : null}
      <button
        type="button"
        className={styles.copy}
        aria-label={`Copy ${relative}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          void copyText(relative);
        }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <rect
            x="5.2"
            y="5.2"
            width="7.2"
            height="7.2"
            rx="1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
          />
          <path
            d="M3.6 10.2V3.8c0-.3.2-.6.6-.6h6.4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
          />
        </svg>
      </button>
    </li>
  );
}

export function VertexDetail({ entity, graph, onClose }: Props) {
  const relationGroups = buildGraphRelationGroups(entity.id, graph);
  const metaGroups = buildMetaGroups(entity, graph);
  const embedText = `${entity.name}. ${entity.description}`.trim();

  return (
    <div className={styles.root}>
      <button type="button" className={styles.back} onClick={onClose}>
        ← Back to graphs
      </button>
      <h2 className={styles.title}>{entity.name}</h2>
      <section className={styles.section}>
        <h3>Description (embedding text)</h3>
        <p className={styles.description}>
          {entity.description.trim() ? entity.description : <span className={styles.muted}>No description</span>}
        </p>
        <p className={styles.embedHint}>
          Embedded as: <code>{embedText || entity.name}</code>
        </p>
      </section>
      <section className={styles.section}>
        <h3>Files</h3>
        {entity.code_refs.length === 0 ? (
          <p className={styles.muted}>No files</p>
        ) : (
          <ul className={styles.list}>
            {entity.code_refs.map((ref) => (
              <FileEntry key={ref.id} pathRef={ref} />
            ))}
          </ul>
        )}
      </section>
      <section className={styles.section}>
        <h3>Dependencies in this graph</h3>
        {relationGroups.length === 0 ? (
          <p className={styles.muted}>No graph edges for this vertex.</p>
        ) : (
          relationGroups.map((g) => (
            <div key={g.relation} className={styles.group}>
              <div className={styles.groupTitle}>{labelRelation(g.relation)}</div>
              {g.outgoing.length > 0 ? (
                <ul className={styles.list}>
                  {g.outgoing.map((name) => (
                    <li key={`out-${g.relation}-${name}`}>
                      <span className={styles.dir}>→</span> {name}
                    </li>
                  ))}
                </ul>
              ) : null}
              {g.incoming.length > 0 ? (
                <ul className={styles.list}>
                  {g.incoming.map((name) => (
                    <li key={`in-${g.relation}-${name}`}>
                      <span className={styles.dir}>←</span> {name}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))
        )}
      </section>
      {metaGroups.size > 0 ? (
        <section className={styles.section}>
          <h3>Meta-links</h3>
          {[...metaGroups.entries()]
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([relation, peers]) => (
              <div key={relation} className={styles.group}>
                <div className={styles.groupTitle}>{labelRelation(relation)}</div>
                <ul className={styles.list}>
                  {peers.map((name) => (
                    <li key={`${relation}-${name}`}>{name}</li>
                  ))}
                </ul>
              </div>
            ))}
        </section>
      ) : null}
    </div>
  );
}

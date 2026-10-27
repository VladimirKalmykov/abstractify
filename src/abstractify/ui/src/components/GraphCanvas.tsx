import { useEffect, useMemo, useRef } from "react";
import * as d3 from "d3";
import { graphLayoutKey } from "../graphLayoutKey";
import type { Entity, GraphDetail } from "../types";
import styles from "./GraphCanvas.module.css";

type NodeDatum = Entity & d3.SimulationNodeDatum;
type LinkDatum = d3.SimulationLinkDatum<NodeDatum> & {
  relation: string;
  source_id: string;
  target_id: string;
};

const CARD_W = 176;
const CARD_H = 78;
/** Minimum spacing between node centers (card half-diagonal + gap). */
const COLLIDE_RADIUS = 150;
const LINK_DISTANCE = 190;
const CHARGE_STRENGTH = -1100;
const DRAG_CLICK_THRESHOLD = 5;

const STROKE_DEFAULT = "#20e3c8";
const FILL_DEFAULT = "#0b141c";
const GLOW_DEFAULT = "drop-shadow(0 0 6px rgba(32,227,200,0.35))";

/** Selected vertex */
const STROKE_SELECTED = "#f0d048";
const FILL_SELECTED = "#2a2410";
const GLOW_SELECTED = "drop-shadow(0 0 10px rgba(240,208,72,0.55))";
const TITLE_SELECTED = "#fff3c4";

/** Direct neighbors — muted grass green (not UI cyan/teal) */
const STROKE_NEIGHBOR = "#6f9a52";
const FILL_NEIGHBOR = "#121a0f";
const GLOW_NEIGHBOR = "drop-shadow(0 0 8px rgba(111,154,82,0.4))";
const TITLE_NEIGHBOR = "#c8ddb8";

const STROKE_LINK_DEFAULT = "#1a6b66";
const FILL_LINK_LABEL_DEFAULT = "#4aa8a0";

type NodeRole = "selected" | "neighbor" | "default";

function neighborIds(selectedId: string | null, links: LinkDatum[]): Set<string> {
  const ids = new Set<string>();
  if (!selectedId) return ids;
  for (const l of links) {
    if (l.source_id === selectedId) ids.add(l.target_id);
    if (l.target_id === selectedId) ids.add(l.source_id);
  }
  return ids;
}

function nodeRole(id: string, selectedId: string | null, neighbors: Set<string>): NodeRole {
  if (!selectedId) return "default";
  if (id === selectedId) return "selected";
  if (neighbors.has(id)) return "neighbor";
  return "default";
}

type Props = {
  graph: GraphDetail | null;
  selectedEntityId: string | null;
  onSelectEntity: (id: string | null) => void;
};

function linkEndpointId(endpoint: LinkDatum["source"] | LinkDatum["target"], fallback: string): string {
  if (typeof endpoint === "object" && endpoint !== null && "id" in endpoint) {
    return (endpoint as NodeDatum).id;
  }
  return fallback;
}

function linkTouchesSelection(link: LinkDatum, selectedEntityId: string): boolean {
  const sourceId = linkEndpointId(link.source, link.source_id);
  const targetId = linkEndpointId(link.target, link.target_id);
  return sourceId === selectedEntityId || targetId === selectedEntityId;
}

function applyGraphSelection(
  node: d3.Selection<SVGGElement, NodeDatum, SVGGElement, unknown>,
  link: d3.Selection<SVGPathElement, LinkDatum, SVGGElement, unknown>,
  linkLabel: d3.Selection<SVGTextElement, LinkDatum, SVGGElement, unknown>,
  links: LinkDatum[],
  selectedEntityId: string | null,
) {
  const neighbors = neighborIds(selectedEntityId, links);
  node.attr("opacity", (d) => {
    if (!selectedEntityId) return 1;
    const role = nodeRole(d.id, selectedEntityId, neighbors);
    return role === "default" ? 0.42 : 1;
  });
  node.each(function (d) {
    const role = nodeRole(d.id, selectedEntityId, neighbors);
    const g = d3.select(this);
    const card = g.select<SVGRectElement>("rect.node-card");
    const title = g.select<SVGTextElement>("text");
    if (role === "selected") {
      card
        .attr("stroke", STROKE_SELECTED)
        .attr("fill", FILL_SELECTED)
        .attr("stroke-width", 2.5)
        .attr("filter", GLOW_SELECTED);
      title.attr("fill", TITLE_SELECTED);
    } else if (role === "neighbor") {
      card
        .attr("stroke", STROKE_NEIGHBOR)
        .attr("fill", FILL_NEIGHBOR)
        .attr("stroke-width", 2)
        .attr("filter", GLOW_NEIGHBOR);
      title.attr("fill", TITLE_NEIGHBOR);
    } else {
      card
        .attr("stroke", STROKE_DEFAULT)
        .attr("fill", FILL_DEFAULT)
        .attr("stroke-width", 1.15)
        .attr("filter", GLOW_DEFAULT);
      title.attr("fill", "#d6f7f1");
    }
    const accent =
      role === "selected" ? STROKE_SELECTED : role === "neighbor" ? STROKE_NEIGHBOR : STROKE_DEFAULT;
    g.selectAll("g").selectAll("rect,circle,line,polygon").attr("stroke", accent);
  });

  link
    .attr("stroke", (d) =>
      selectedEntityId && linkTouchesSelection(d, selectedEntityId)
        ? STROKE_NEIGHBOR
        : STROKE_LINK_DEFAULT,
    )
    .attr("stroke-width", (d) =>
      selectedEntityId && linkTouchesSelection(d, selectedEntityId) ? 2 : 1.1,
    )
    .attr("opacity", (d) => {
      if (!selectedEntityId) return 0.9;
      return linkTouchesSelection(d, selectedEntityId) ? 1 : 0.22;
    });

  linkLabel
    .attr("fill", (d) =>
      selectedEntityId && linkTouchesSelection(d, selectedEntityId)
        ? TITLE_NEIGHBOR
        : FILL_LINK_LABEL_DEFAULT,
    )
    .attr("opacity", (d) => {
      if (!selectedEntityId) return 1;
      return linkTouchesSelection(d, selectedEntityId) ? 1 : 0.28;
    });
}

export function GraphCanvas({ graph, selectedEntityId, onSelectEntity }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const onSelectRef = useRef(onSelectEntity);
  onSelectRef.current = onSelectEntity;
  const layoutKey = useMemo(() => graphLayoutKey(graph), [graph]);
  const graphRef = useRef(graph);
  graphRef.current = graph;
  const nodeLayerRef = useRef<d3.Selection<SVGGElement, NodeDatum, SVGGElement, unknown> | null>(
    null,
  );
  const linksRef = useRef<LinkDatum[]>([]);
  const linkLayerRef = useRef<d3.Selection<SVGPathElement, LinkDatum, SVGGElement, unknown> | null>(
    null,
  );
  const linkLabelLayerRef = useRef<d3.Selection<
    SVGTextElement,
    LinkDatum,
    SVGGElement,
    unknown
  > | null>(null);

  useEffect(() => {
    const graph = graphRef.current;
    const svgEl = svgRef.current;
    const wrap = wrapRef.current;
    if (!svgEl || !wrap || !graph || !layoutKey) return;

    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();

    const width = wrap.clientWidth || 800;
    const height = wrap.clientHeight || 600;

    const root = svg.append("g");
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.25, 4])
      .on("zoom", (event) => {
        root.attr("transform", event.transform.toString());
      });
    svg.call(zoom);

    root
      .append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "transparent")
      .attr("pointer-events", "all")
      .on("click", () => onSelectRef.current(null));

    const nodes: NodeDatum[] = graph.entities.map((e) => ({ ...e }));
    const idSet = new Set(nodes.map((n) => n.id));
    const links: LinkDatum[] = graph.edges
      .filter((e) => idSet.has(e.source_id) && idSet.has(e.target_id))
      .map((e) => ({
        source: e.source_id,
        target: e.target_id,
        source_id: e.source_id,
        target_id: e.target_id,
        relation: e.relation,
      }));

    const sim = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<NodeDatum, LinkDatum>(links)
          .id((d) => d.id)
          .distance(LINK_DISTANCE),
      )
      .force("charge", d3.forceManyBody().strength(CHARGE_STRENGTH))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(COLLIDE_RADIUS));

    const link = root
      .append("g")
      .attr("fill", "none")
      .selectAll("path")
      .data(links)
      .enter()
      .append("path")
      .attr("stroke", "#1a6b66")
      .attr("stroke-width", 1.1)
      .attr("opacity", 0.9);

    const linkLabel = root
      .append("g")
      .selectAll("text")
      .data(links)
      .enter()
      .append("text")
      .attr("fill", "#4aa8a0")
      .attr("font-size", 9)
      .attr("font-family", "IBM Plex Mono, ui-monospace, monospace")
      .attr("text-anchor", "middle")
      .text((d) => d.relation.replaceAll("_", " "));

    const node = root
      .append("g")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .attr("cursor", "grab")
      .call(
        d3
          .drag<SVGGElement, NodeDatum>()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.25).restart();
            d.fx = d.x;
            d.fy = d.y;
            const src = event.sourceEvent as MouseEvent | TouchEvent | undefined;
            const pt =
              src && "clientX" in src
                ? { x: src.clientX, y: src.clientY }
                : src && "touches" in src && src.touches[0]
                  ? { x: src.touches[0].clientX, y: src.touches[0].clientY }
                  : { x: 0, y: 0 };
            (d as NodeDatum & { _pressX?: number; _pressY?: number })._pressX = pt.x;
            (d as NodeDatum & { _pressY?: number })._pressY = pt.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            const src = event.sourceEvent as MouseEvent | TouchEvent | undefined;
            const pt =
              src && "clientX" in src
                ? { x: src.clientX, y: src.clientY }
                : src && "changedTouches" in src && src.changedTouches[0]
                  ? { x: src.changedTouches[0].clientX, y: src.changedTouches[0].clientY }
                  : { x: 0, y: 0 };
            const pressX = (d as NodeDatum & { _pressX?: number })._pressX ?? pt.x;
            const pressY = (d as NodeDatum & { _pressY?: number })._pressY ?? pt.y;
            const moved = Math.hypot(pt.x - pressX, pt.y - pressY);
            if (moved < DRAG_CLICK_THRESHOLD) {
              event.sourceEvent?.stopPropagation?.();
              onSelectRef.current(d.id);
            }
            d.fx = null;
            d.fy = null;
          }),
      );

    node
      .append("rect")
      .attr("class", "node-card")
      .attr("x", -CARD_W / 2)
      .attr("y", -CARD_H / 2)
      .attr("width", CARD_W)
      .attr("height", CARD_H)
      .attr("rx", 8)
      .attr("ry", 8)
      .attr("fill", "#0b141c")
      .attr("stroke", "#20e3c8")
      .attr("stroke-width", 1.15)
      .attr("filter", "drop-shadow(0 0 6px rgba(32,227,200,0.35))");

    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("y", -8)
      .attr("fill", "#d6f7f1")
      .attr("font-size", 13)
      .attr("font-weight", 600)
      .text((d) => truncate(d.name, 22));

    const counts = node.append("g").attr("transform", `translate(0, ${CARD_H / 2 - 16})`);
    drawCount(counts, -56, "file", (d) => d.code_ref_count);
    drawCount(counts, 0, "link", (d) => d.degree);
    drawCount(counts, 56, "meta", (d) => d.meta_link_count);

    linksRef.current = links;
    nodeLayerRef.current = node;
    linkLayerRef.current = link;
    linkLabelLayerRef.current = linkLabel;

    sim.on("tick", () => {
      link.attr("d", (d) => {
        const s = d.source as NodeDatum;
        const t = d.target as NodeDatum;
        return `M${s.x},${s.y} L${t.x},${t.y}`;
      });
      linkLabel.attr("x", (d) => mid(d, "x")).attr("y", (d) => mid(d, "y") - 6);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      sim.stop();
      nodeLayerRef.current = null;
      linksRef.current = [];
      linkLayerRef.current = null;
      linkLabelLayerRef.current = null;
    };
  }, [layoutKey]);

  useEffect(() => {
    const node = nodeLayerRef.current;
    const link = linkLayerRef.current;
    const linkLabel = linkLabelLayerRef.current;
    if (!node || !link || !linkLabel) return;
    applyGraphSelection(node, link, linkLabel, linksRef.current, selectedEntityId);
  }, [selectedEntityId, layoutKey]);

  useEffect(() => {
    if (layoutKey !== null) return;
    const svgEl = svgRef.current;
    if (svgEl) d3.select(svgEl).selectAll("*").remove();
    nodeLayerRef.current = null;
    linksRef.current = [];
    linkLayerRef.current = null;
    linkLabelLayerRef.current = null;
  }, [layoutKey]);

  return (
    <div className={styles.wrap} ref={wrapRef}>
      {graph ? (
        <div className={styles.principle}>
          <strong>{graph.kind}</strong>
          {graph.principle || graph.name}
        </div>
      ) : (
        <div className={styles.empty}>Select a graph</div>
      )}
      <svg ref={svgRef} className={styles.svg} />
    </div>
  );
}

function mid(d: LinkDatum, axis: "x" | "y"): number {
  const s = d.source as NodeDatum;
  const t = d.target as NodeDatum;
  const a = (s[axis] ?? 0) as number;
  const b = (t[axis] ?? 0) as number;
  return (a + b) / 2;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function drawCount(
  sel: d3.Selection<SVGGElement, NodeDatum, SVGGElement, unknown>,
  x: number,
  kind: "file" | "link" | "meta",
  value: (d: NodeDatum) => number,
) {
  const g = sel.append("g").attr("transform", `translate(${x}, 0)`);
  if (kind === "file") {
    g.append("rect")
      .attr("x", -18)
      .attr("y", -7)
      .attr("width", 8)
      .attr("height", 10)
      .attr("rx", 1)
      .attr("fill", "none")
      .attr("stroke", "#20e3c8")
      .attr("stroke-width", 1);
  } else if (kind === "link") {
    g.append("circle")
      .attr("cx", -16)
      .attr("cy", -2)
      .attr("r", 2.4)
      .attr("fill", "none")
      .attr("stroke", "#20e3c8");
    g.append("circle")
      .attr("cx", -10)
      .attr("cy", -2)
      .attr("r", 2.4)
      .attr("fill", "none")
      .attr("stroke", "#20e3c8");
    g.append("line")
      .attr("x1", -14)
      .attr("y1", -2)
      .attr("x2", -12)
      .attr("y2", -2)
      .attr("stroke", "#20e3c8");
  } else {
    g.append("polygon")
      .attr("points", "-18,-6 -12,-2 -18,2")
      .attr("fill", "none")
      .attr("stroke", "#20e3c8")
      .attr("stroke-width", 1);
  }
  g.append("text")
    .attr("x", -4)
    .attr("y", 2)
    .attr("fill", "#8fdcd3")
    .attr("font-size", 10)
    .attr("font-family", "IBM Plex Mono, ui-monospace, monospace")
    .text((d) => String(value(d)));
}

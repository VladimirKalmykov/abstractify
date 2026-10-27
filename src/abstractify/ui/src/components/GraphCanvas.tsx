import { useEffect, useRef } from "react";
import * as d3 from "d3";
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

export function GraphCanvas({ graph }: { graph: GraphDetail | null }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svgEl = svgRef.current;
    const wrap = wrapRef.current;
    if (!svgEl || !wrap || !graph) return;

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
          .distance(170),
      )
      .force("charge", d3.forceManyBody().strength(-420))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(90));

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
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    node
      .append("rect")
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
    };
  }, [graph]);

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

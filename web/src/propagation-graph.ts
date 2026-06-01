import { DataSet } from "vis-data";
import { Network } from "vis-network";
import "vis-network/styles/vis-network.min.css";

import type { CibReport, PropagationGraph } from "./types";

export type GraphTopology = "star" | "distributed" | "sparse" | "isolated";

export interface GraphLayoutMeta {
  topology: GraphTopology;
  hubAuthorId: string | null;
  hubShare: number;
  nodeCount: number;
  edgeCount: number;
}

let activeNetwork: Network | null = null;

function truncateId(id: string, n = 10): string {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function outrageColor(score: number): string {
  const t = Math.min(1, Math.max(0, score));
  const r = Math.round(120 + t * 135);
  const g = Math.round(80 - t * 50);
  const b = Math.round(90 - t * 60);
  return `rgb(${r},${g},${b})`;
}

export function analyzeTopology(
  graph: PropagationGraph,
  cib: CibReport
): GraphLayoutMeta {
  const edges = graph.edges;
  const edgeCount = edges.length;
  const authors = graph.authors;
  const nodeCount = authors.length;

  if (edgeCount === 0) {
    return {
      topology: nodeCount > 0 ? "isolated" : "sparse",
      hubAuthorId: null,
      hubShare: 0,
      nodeCount,
      edgeCount,
    };
  }

  const outDegree = new Map<string, number>();
  for (const e of edges) {
    outDegree.set(e.source, (outDegree.get(e.source) ?? 0) + 1);
  }

  let hubAuthorId: string | null = null;
  let maxOut = 0;
  for (const [author, deg] of outDegree) {
    if (deg > maxOut) {
      maxOut = deg;
      hubAuthorId = author;
    }
  }

  const hubShare = maxOut / edgeCount;
  const amplifiersWithOut = [...outDegree.values()].filter((d) => d > 0).length;

  let topology: GraphTopology = "distributed";
  if (hubShare > 0.5 && maxOut >= 2) {
    topology = "star";
  } else if (edgeCount < 3 || amplifiersWithOut <= 1) {
    topology = "sparse";
  } else if (cib.signals.some((s) => s.includes("single_hub"))) {
    topology = "star";
  }

  return { topology, hubAuthorId, hubShare, nodeCount, edgeCount };
}

function topologyCaption(meta: GraphLayoutMeta): string {
  switch (meta.topology) {
    case "star":
      return "Star topology: one hub accounts for most share edges (coordinated amplification pattern).";
    case "distributed":
      return "Distributed topology: multiple amplifiers; resembles organic multi-hub spread.";
    case "isolated":
      return "Authors present but no propagation edges in ingest (cannot assess share shape).";
    default:
      return "Sparse graph: few edges relative to authors.";
  }
}

export function renderPropagationGraph(
  container: HTMLElement,
  graph: PropagationGraph,
  cib: CibReport
): GraphLayoutMeta {
  if (activeNetwork) {
    activeNetwork.destroy();
    activeNetwork = null;
  }

  const meta = analyzeTopology(graph, cib);
  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  for (const e of graph.edges) {
    outDegree.set(e.source, (outDegree.get(e.source) ?? 0) + 1);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }

  const ampById = new Map(cib.top_amplifiers.map((a) => [a.author_id, a]));

  const nodes = new DataSet(
    graph.authors.map((a) => {
      const out = outDegree.get(a.author_id) ?? ampById.get(a.author_id)?.out_degree ?? 0;
      const inn = inDegree.get(a.author_id) ?? ampById.get(a.author_id)?.in_degree ?? 0;
      const isHub = meta.hubAuthorId === a.author_id && meta.topology === "star";
      const label = a.handle ? `@${a.handle}` : truncateId(a.author_id);
      return {
        id: a.author_id,
        label,
        title: `${a.author_id}\nposts: ${a.post_count} · out: ${out} · in: ${inn}\nmax outrage: ${a.max_outrage.toFixed(2)}${a.known_bot ? "\nIU known bot" : ""}`,
        size: 12 + Math.min(28, out * 4 + a.post_count * 2),
        color: {
          background: outrageColor(a.max_outrage),
          border: isHub ? "#f5a623" : a.known_bot ? "#9b59b6" : "#2a384c",
          highlight: { background: "#c0392b", border: "#fff" },
        },
        borderWidth: isHub ? 4 : 2,
        font: { color: "#e8edf4", size: 12 },
        shape: a.known_bot ? "diamond" : "dot",
      };
    })
  );

  const edges = new DataSet(
    graph.edges.map((e, i) => ({
      id: i,
      from: e.source,
      to: e.target,
      arrows: "to",
      title: e.type,
      color: {
        color: e.source === meta.hubAuthorId ? "rgba(245,166,35,0.75)" : "rgba(42,56,76,0.9)",
        highlight: "#c0392b",
      },
      width: e.source === meta.hubAuthorId ? 2.5 : 1.2,
    }))
  );

  const options = {
    physics: {
      enabled: true,
      stabilization: { iterations: 150 },
      barnesHut: {
        gravitationalConstant: -9000,
        springLength: meta.topology === "star" ? 180 : 130,
        springConstant: 0.04,
      },
    },
    interaction: {
      hover: true,
      tooltipDelay: 80,
      zoomView: true,
      dragView: true,
    },
    layout: {
      improvedLayout: graph.authors.length < 80,
    },
  };

  activeNetwork = new Network(container, { nodes, edges }, options);

  const legend = container.parentElement?.querySelector(".graph-legend");
  if (legend) {
    legend.textContent = topologyCaption(meta);
  }

  return meta;
}

export function graphPanelHtml(meta: GraphLayoutMeta | null): string {
  const badge =
    meta?.topology === "star"
      ? '<span class="topology-badge topology-star">star / coordinated</span>'
      : meta?.topology === "distributed"
        ? '<span class="topology-badge topology-organic">distributed / organic-like</span>'
        : meta?.topology === "isolated"
          ? '<span class="topology-badge topology-isolated">no edges</span>'
          : '<span class="topology-badge topology-sparse">sparse</span>';

  return `
    <section class="panel graph-panel">
      <h2>Propagation network ${badge}</h2>
      <p class="graph-legend">Loading graph…</p>
      <div id="propagation-graph" class="graph-canvas" role="img" aria-label="Author propagation network"></div>
      <p class="metric-sub graph-hint">Drag to pan · scroll to zoom · hover nodes for author stats</p>
    </section>
  `;
}

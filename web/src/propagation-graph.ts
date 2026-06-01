import { DataSet } from "vis-data";
import { Network } from "vis-network";
import "vis-network/styles/vis-network.min.css";

import type { CibReport, GraphEdge, PropagationGraph } from "./types";

interface AggregatedEdge {
  id: string;
  from: string;
  to: string;
  weight: number;
  types: string[];
}

export type GraphTopology = "star" | "distributed" | "sparse" | "isolated";

export interface GraphLayoutMeta {
  topology: GraphTopology;
  hubAuthorId: string | null;
  hubShare: number;
  nodeCount: number;
  edgeCount: number;
}

let activeNetwork: Network | null = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let activeEdges: DataSet<any> | null = null;
let aggregatedEdges: AggregatedEdge[] = [];
let graphMeta: GraphLayoutMeta | null = null;
let physicsFrozen = false;
let onAuthorClick: ((authorId: string) => void) | null = null;

function aggregateEdges(raw: GraphEdge[]): AggregatedEdge[] {
  const map = new Map<string, AggregatedEdge>();
  for (const e of raw) {
    const id = `${e.source}→${e.target}`;
    const existing = map.get(id);
    if (existing) {
      existing.weight += 1;
      if (!existing.types.includes(e.type)) existing.types.push(e.type);
    } else {
      map.set(id, {
        id,
        from: e.source,
        to: e.target,
        weight: 1,
        types: [e.type],
      });
    }
  }
  return [...map.values()];
}

function maxEdgeWeight(edges: AggregatedEdge[]): number {
  return edges.reduce((m, e) => Math.max(m, e.weight), 1);
}

function applyEdgeWeightFilter(minWeight: number): void {
  if (!activeEdges) return;
  const updates = aggregatedEdges.map((e) => ({
    id: e.id,
    hidden: e.weight < minWeight,
  }));
  activeEdges.update(updates);

  const visible = aggregatedEdges.filter((e) => e.weight >= minWeight).length;
  const label = document.getElementById("edge-filter-status");
  if (label) {
    label.textContent =
      minWeight <= 1
        ? `${aggregatedEdges.length} edges`
        : `${visible} / ${aggregatedEdges.length} edges (weight ≥ ${minWeight})`;
  }
}

function setPhysicsEnabled(enabled: boolean): void {
  if (!activeNetwork) return;
  physicsFrozen = !enabled;
  activeNetwork.setOptions({ physics: { enabled } });
  const btn = document.getElementById("freeze-physics-btn");
  if (btn) {
    btn.textContent = enabled ? "Freeze layout" : "Resume physics";
    btn.setAttribute("aria-pressed", enabled ? "false" : "true");
  }
}

export function bindPropagationGraphControls(): void {
  const slider = document.getElementById("edge-weight-filter") as HTMLInputElement | null;
  const valueEl = document.getElementById("edge-weight-value");
  const freezeBtn = document.getElementById("freeze-physics-btn");

  if (slider && aggregatedEdges.length > 0) {
    const maxW = maxEdgeWeight(aggregatedEdges);
    slider.min = "1";
    slider.max = String(maxW);
    slider.value = "1";
    slider.disabled = maxW <= 1;
    if (valueEl) valueEl.textContent = "1";
    applyEdgeWeightFilter(1);

    slider.oninput = () => {
      const minW = parseInt(slider.value, 10) || 1;
      if (valueEl) valueEl.textContent = String(minW);
      applyEdgeWeightFilter(minW);
    };
  }

  if (freezeBtn) {
    freezeBtn.onclick = () => setPhysicsEnabled(physicsFrozen);
  }
}

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

export function focusPropagationAuthor(authorId: string | null): void {
  if (!activeNetwork) return;
  if (!authorId) {
    activeNetwork.unselectAll();
    return;
  }
  activeNetwork.selectNodes([authorId]);
  activeNetwork.focus(authorId, {
    scale: 1.15,
    animation: {
      duration: 480,
      easingFunction: "easeInOutQuad",
    },
  });
}

export function setPropagationAuthorHandler(
  handler: ((authorId: string) => void) | null
): void {
  onAuthorClick = handler;
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

  aggregatedEdges = aggregateEdges(graph.edges);
  graphMeta = analyzeTopology(graph, cib);
  const meta = graphMeta;
  physicsFrozen = false;

  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  for (const e of aggregatedEdges) {
    outDegree.set(e.from, (outDegree.get(e.from) ?? 0) + e.weight);
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + e.weight);
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
    aggregatedEdges.map((e) => ({
      id: e.id,
      from: e.from,
      to: e.to,
      value: e.weight,
      arrows: "to",
      title: `${e.types.join(", ")} · weight ${e.weight}`,
      color: {
        color:
          e.from === meta.hubAuthorId
            ? "rgba(245,166,35,0.75)"
            : "rgba(42,56,76,0.9)",
        highlight: "#c0392b",
      },
      width: Math.min(6, 1 + e.weight * 0.65),
      hidden: false,
    }))
  );
  activeEdges = edges;

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

  activeNetwork.off("click");
  activeNetwork.on("click", (params) => {
    const nodeId = params.nodes[0];
    if (nodeId && onAuthorClick) {
      onAuthorClick(String(nodeId));
    }
  });

  const legend = container.parentElement?.querySelector(".graph-legend");
  if (legend) {
    legend.textContent = topologyCaption(meta);
  }

  bindPropagationGraphControls();

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
    <section class="panel graph-panel" id="propagation-graph-panel">
      <h2>Propagation network ${badge}</h2>
      <p class="graph-legend">Loading graph…</p>
      <div class="graph-controls">
        <label class="graph-control">
          <span>Min edge weight <strong id="edge-weight-value">1</strong></span>
          <input
            type="range"
            id="edge-weight-filter"
            min="1"
            max="1"
            value="1"
            aria-label="Minimum edge weight to display"
          />
        </label>
        <span class="graph-control-status" id="edge-filter-status"></span>
        <button
          type="button"
          id="freeze-physics-btn"
          class="btn btn-secondary btn-small"
          aria-pressed="false"
        >
          Freeze layout
        </button>
      </div>
      <div id="propagation-graph" class="graph-canvas" role="img" aria-label="Author propagation network"></div>
      <p class="metric-sub graph-hint">Raise min weight to hide single-share links · freeze layout after it settles · click nodes to filter posts</p>
    </section>
  `;
}

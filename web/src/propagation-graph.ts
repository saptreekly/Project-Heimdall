import { DataSet } from "vis-data";
import { Network } from "vis-network";
import "vis-network/styles/vis-network.min.css";

import type { CibReport, GraphEdge, GraphInteractionStats, PropagationGraph } from "./types";

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

const EDGE_TYPE_LABELS: Record<string, string> = {
  share: "Share / RT",
  retweet: "Retweet",
  reply: "Reply",
  quote: "Quote",
};

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
    const t = (e.type || "unknown").toLowerCase();
    const existing = map.get(id);
    if (existing) {
      existing.weight += 1;
      if (!existing.types.includes(t)) existing.types.push(t);
    } else {
      map.set(id, {
        id,
        from: e.source,
        to: e.target,
        weight: 1,
        types: [t],
      });
    }
  }
  return [...map.values()];
}

function maxEdgeWeight(edges: AggregatedEdge[]): number {
  return edges.reduce((m, e) => Math.max(m, e.weight), 1);
}

function primaryEdgeType(types: string[]): string {
  const order = ["share", "retweet", "quote", "reply"];
  for (const t of order) {
    if (types.includes(t)) return t;
  }
  return types[0] ?? "unknown";
}

function edgeColorForTypes(types: string[], hubAuthorId: string | null, from: string): string {
  const primary = primaryEdgeType(types);
  if (from === hubAuthorId) return "rgba(245,166,35,0.9)";
  if (primary === "quote") return "rgba(187,143,206,0.9)";
  if (primary === "reply") return "rgba(93,173,226,0.9)";
  if (primary === "share" || primary === "retweet") return "rgba(245,166,35,0.75)";
  return "rgba(42,56,76,0.9)";
}

function edgeDashForTypes(types: string[]): number[] | undefined {
  const primary = primaryEdgeType(types);
  if (primary === "reply") return [6, 4];
  if (primary === "quote") return [2, 3];
  return undefined;
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

function formatTypeBreakdown(byType: Record<string, number>): string {
  const parts = Object.entries(byType)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => `${EDGE_TYPE_LABELS[t] ?? t}: ${n}`);
  return parts.length ? parts.join(" · ") : "none recorded";
}

export function renderGraphDiagnostics(
  host: HTMLElement,
  graph: PropagationGraph,
  meta: GraphLayoutMeta
): void {
  const stats: GraphInteractionStats = graph.stats ?? {
    edge_count: graph.edges.length,
    author_count: graph.authors.length,
    connected_author_count: 0,
    isolated_author_count: graph.authors.length,
    by_type: {},
  };

  const empty = stats.edge_count === 0;
  host.innerHTML = empty
    ? `
    <details class="graph-text-summary" open>
      <summary>Text summary of graph</summary>
      <div class="graph-diagnostics graph-diagnostics-empty" role="status">
        <p class="graph-diagnostics-title"><strong>No propagation edges in this snapshot</strong></p>
        <p class="graph-diagnostics-body">
          ${stats.author_count} author(s) ingested · ${stats.isolated_author_count} with no SHARE, REPLY, or QUOTE target in the batch.
          Search-only X pulls often miss retweet/reply/quote metadata until those interaction types appear in results.
        </p>
        <ul class="graph-diagnostics-list">
          <li>Re-run ingest after deploying reply/quote edge parsing (Phase 1).</li>
          <li>Check <strong>Network</strong> and duplicate panels for text-level coordination meanwhile.</li>
          <li>List timelines (<code>list:&lt;id&gt;</code>) can surface more retweets than keyword search alone.</li>
        </ul>
      </div>
    </details>
  `
    : `
    <details class="graph-text-summary" open>
      <summary>Text summary of graph</summary>
      <div class="graph-diagnostics" role="status">
        <p class="graph-diagnostics-metrics">
          <strong>${stats.edge_count}</strong> edge(s) ·
          <strong>${stats.author_count}</strong> authors ·
          <strong>${stats.connected_author_count}</strong> in network ·
          <strong>${stats.isolated_author_count}</strong> isolated
        </p>
        <p class="graph-diagnostics-types">${formatTypeBreakdown(stats.by_type)}</p>
        <p class="graph-diagnostics-topology">${topologyCaption(meta)}</p>
      </div>
    </details>
  `;
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

  const emptyHost = document.getElementById("graph-empty-state");
  const canvasWrap = document.getElementById("propagation-graph-wrap");
  const controls = document.getElementById("graph-controls-row");
  const isEmpty = graph.edges.length === 0;

  if (emptyHost) {
    if (isEmpty) {
      emptyHost.hidden = false;
      emptyHost.innerHTML =
        "<p class=\"graph-empty-placeholder\">No edges to render — ingest SHARE, REPLY, or QUOTE interactions, then re-export the snapshot.</p>";
    } else {
      emptyHost.hidden = true;
      emptyHost.innerHTML = "";
    }
  }
  if (canvasWrap) {
    canvasWrap.hidden = isEmpty;
  }
  if (controls) {
    controls.hidden = isEmpty;
  }

  const diagHost = document.getElementById("graph-diagnostics-host");
  if (diagHost) {
    renderGraphDiagnostics(diagHost, graph, meta);
  }

  if (isEmpty) {
    container.innerHTML = "";
    const legend = container.parentElement?.querySelector(".graph-legend");
    if (legend) {
      legend.textContent = topologyCaption(meta);
    }
    return meta;
  }

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
      title: `${e.types.map((t) => EDGE_TYPE_LABELS[t] ?? t).join(" + ")} · weight ${e.weight}`,
      color: {
        color: edgeColorForTypes(e.types, meta.hubAuthorId, e.from),
        highlight: "#c0392b",
      },
      dashes: edgeDashForTypes(e.types),
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

export function graphPanelHtml(): string {
  return `
    <section class="panel graph-panel" id="propagation-graph-panel">
      <div class="graph-panel-header">
        <h2 id="propagation-graph-heading">Propagation network</h2>
        <button type="button" id="graph-fullscreen-btn" class="btn btn-secondary btn-small graph-fullscreen-btn" aria-pressed="false">Fullscreen</button>
      </div>
      <div id="graph-diagnostics-host" class="graph-diagnostics-host"></div>
      <p class="graph-legend">Loading graph…</p>
      <div class="graph-edge-legend" aria-hidden="false">
        <span class="graph-edge-key graph-edge-key-share">Share / RT</span>
        <span class="graph-edge-key graph-edge-key-reply">Reply</span>
        <span class="graph-edge-key graph-edge-key-quote">Quote</span>
      </div>
      <div id="graph-empty-state" class="graph-empty-state" hidden></div>
      <div id="graph-controls-row" class="graph-controls">
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
      <div id="propagation-graph-wrap" class="graph-canvas-wrap">
        <div id="propagation-graph" class="graph-canvas" role="img" aria-label="Author propagation network"></div>
      </div>
      <p class="metric-sub graph-hint">Edge colors: orange = share/RT · blue dashed = reply · purple dotted = quote · click nodes to filter posts</p>
    </section>
  `;
}

export function bindGraphFullscreen(): void {
  const btn = document.getElementById("graph-fullscreen-btn");
  const panel = document.getElementById("propagation-graph-panel");
  if (!btn || !panel) return;

  btn.addEventListener("click", () => {
    const on = panel.classList.toggle("graph-fullscreen");
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Exit fullscreen" : "Fullscreen";
    document.body.classList.toggle("graph-fullscreen-active", on);
    activeNetwork?.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
  });
}

export function updatePropagationGraphBadge(meta: GraphLayoutMeta): void {
  const badgeHost = document.getElementById("propagation-graph-heading");
  if (!badgeHost) return;
  const badge =
    meta.topology === "star"
      ? '<span class="topology-badge topology-star">star / coordinated</span>'
      : meta.topology === "distributed"
        ? '<span class="topology-badge topology-organic">distributed / organic-like</span>'
        : meta.topology === "isolated"
          ? '<span class="topology-badge topology-isolated">no edges</span>'
          : '<span class="topology-badge topology-sparse">sparse</span>';
  badgeHost.innerHTML = `Propagation network ${badge}`;
}

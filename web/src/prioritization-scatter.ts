import {
  Chart,
  Legend,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  type ChartConfiguration,
} from "chart.js";

import {
  OUTRAGE_COMPRESSION_THRESHOLD,
  scatterOutrageFloorNoticeHtml,
  yPercentile75,
  type OutrageDiagnostics,
} from "./outrage-diagnostics";
import type { CibReport, GraphAuthor, Post, PropagationGraph } from "./types";
import { stateEmptyHtml } from "./ui-states";

Chart.register(ScatterController, PointElement, LinearScale, Tooltip, Legend);

export interface AuthorPriorityPoint {
  author_id: string;
  label: string;
  x: number;
  y: number;
  known_bot: boolean;
  critical: boolean;
  post_count: number;
}

let activeChart: Chart | null = null;
let scatterPools: AuthorPriorityPoint[][] = [];

const COLORS = {
  text: "#8b9cb3",
  grid: "#2a384c",
  gridSubtle: "#1f2a3a",
  bot: "#ff2d2d",
  botBorder: "#ffffff",
  author: "rgba(100, 149, 237, 0.75)",
  critical: "#f5a623",
  criticalBorder: "#fff8e7",
  quadrant: "rgba(245, 166, 35, 0.35)",
};

function truncateId(id: string, n = 12): string {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function hasSpread(values: number[], epsilon = 1e-9): boolean {
  if (values.length < 2) return false;
  return Math.max(...values) - Math.min(...values) > epsilon;
}

function outDegreeByAuthor(graph: PropagationGraph): Map<string, number> {
  const out = new Map<string, number>();
  for (const edge of graph.edges) {
    out.set(edge.source, (out.get(edge.source) ?? 0) + 1);
  }
  return out;
}

function knownBotIds(graph: PropagationGraph, cib: CibReport): Set<string> {
  const ids = new Set<string>();
  for (const a of graph.authors) {
    if (a.known_bot) ids.add(a.author_id);
  }
  const labeled = cib.iu_astroturf?.labeled_accounts;
  if (Array.isArray(labeled)) {
    for (const row of labeled) {
      if (row && typeof row === "object" && "author_id" in row) {
        const id = String((row as { author_id: string }).author_id);
        if (id) ids.add(id);
      }
    }
  }
  return ids;
}

function mergeAuthors(
  graph: PropagationGraph,
  posts: Post[]
): GraphAuthor[] {
  const byId = new Map<string, GraphAuthor>();
  for (const a of graph.authors) {
    byId.set(a.author_id, { ...a });
  }
  for (const p of posts) {
    const outrage = p.outrage_index ?? 0;
    const existing = byId.get(p.author_id);
    if (!existing) {
      byId.set(p.author_id, {
        author_id: p.author_id,
        handle: null,
        max_outrage: outrage,
        post_count: 1,
      });
    } else {
      existing.post_count += 1;
      existing.max_outrage = Math.max(existing.max_outrage, outrage);
    }
  }
  return [...byId.values()];
}

export function hasPropagationSpread(graph: PropagationGraph): boolean {
  return graph.edges.length > 0;
}

export function buildAuthorPriorityPoints(
  graph: PropagationGraph,
  cib: CibReport,
  posts: Post[]
): AuthorPriorityPoint[] {
  const noSpread = !hasPropagationSpread(graph);
  const outDeg = outDegreeByAuthor(graph);
  const bots = knownBotIds(graph, cib);
  const ampById = new Map(cib.top_amplifiers.map((a) => [a.author_id, a]));
  const authors = mergeAuthors(graph, posts);

  const raw = authors.map((a) => {
    const x =
      outDeg.get(a.author_id) ??
      ampById.get(a.author_id)?.out_degree ??
      0;
    const y = Math.max(
      a.max_outrage,
      ampById.get(a.author_id)?.max_outrage ?? 0
    );
    const label = a.handle ? `@${a.handle}` : truncateId(a.author_id);
    return {
      author_id: a.author_id,
      label,
      x,
      y,
      known_bot: bots.has(a.author_id),
      critical: false,
      post_count: a.post_count,
    };
  });

  const xMid = median(raw.map((p) => p.x));
  const yMid = median(raw.map((p) => p.y));
  const maxY = Math.max(...raw.map((p) => p.y), 0);
  const yCompressed = maxY <= OUTRAGE_COMPRESSION_THRESHOLD;
  const yP75 = yPercentile75(raw);

  return raw.map((p) => ({
    ...p,
    critical: noSpread
      ? yCompressed
        ? p.y >= yP75 && p.y > 0 && (maxY <= 0 ? true : p.y >= maxY * 0.85)
        : p.y >= yMid && p.y >= 0.25
      : yCompressed
        ? p.y >= yP75 && p.x >= xMid
        : p.x >= xMid && p.y >= yMid && (p.x > 0 || p.y >= 0.25),
  }));
}

function noSpreadNoticeHtml(edgeCount: number): string {
  if (edgeCount > 0) return "";
  return `
    <div class="scatter-diagnosis" role="status" id="scatter-diagnosis">
      <p class="scatter-diagnosis-title">X-axis wall (out-degree = 0)</p>
      <p>
        Every author stacks on the vertical line at <strong>X = 0</strong> because this snapshot has
        <strong>no propagation edges</strong> (${edgeCount} SHARE/REPLY links in ingest).
        Search-only X pulls often capture standalone posts without retweet or reply targets in the batch,
        so spread cannot be measured on this chart until interactions are ingested.
      </p>
      <p class="scatter-diagnosis-sub">
        Confirm in
        <a href="#propagation-graph-panel">Propagation network</a> (badge: <em>no edges</em>).
        Prefer Pulse → text coordination and Network for copypasta/fuzzy clusters until edges exist.
      </p>
    </div>
  `;
}

function priorityExplainerHtml(edgeCount: number, outrageDiag: OutrageDiagnostics): string {
  const noSpread = edgeCount === 0;
  const yCompressed = outrageDiag.compressed;

  let rankingNote: string;
  if (noSpread && yCompressed) {
    rankingNote =
      "This snapshot has <strong>no propagation edges</strong> and <strong>low outrage scores</strong>, so the chart cannot rank spread × toxicity. The list below flags <em>relative targets</em> — authors in the top outrage tier for this narrative, not necessarily high absolute threat.";
  } else if (noSpread) {
    rankingNote =
      "Spread (X) is unavailable — no retweet/reply edges in ingest. The list ranks by <strong>outrage only</strong>. Use Network and text coordination for copypasta signals.";
  } else if (yCompressed) {
    rankingNote =
      "Outrage scores are compressed near the lexicon floor. Flagged authors are high <em>relative to this narrative</em>; check duplicate-text and theme panels for coordination without high outrage.";
  } else {
    rankingNote =
      "Authors in the <strong>top-right</strong> (high spread and high outrage) are flagged as critical targets — the usual starting point for investigation.";
  }

  return `
    <details class="priority-explainer" open>
      <summary>What this chart shows</summary>
      <div class="priority-explainer-body">
        <p>
          Each dot is one account in this narrative. The chart helps you decide <strong>who to investigate first</strong>
          by plotting two signals at once:
        </p>
        <dl class="priority-explainer-axes">
          <div>
            <dt>Horizontal (X) — Out-degree · spread</dt>
            <dd>How many other authors this account amplified (retweets, replies, shares). Further right = wider reach in the propagation graph.</dd>
          </div>
          <div>
            <dt>Vertical (Y) — Max outrage index</dt>
            <dd>The highest outrage score among this author’s posts (0–1 from the lexicon). Higher = more inflammatory language in their worst post.</dd>
          </div>
        </dl>
        <p>${rankingNote}</p>
        <p class="priority-explainer-legend">
          <span class="priority-legend-dot priority-legend-author"></span> Author
          <span class="priority-legend-dot priority-legend-critical"></span> Flagged target
          <span class="priority-legend-dot priority-legend-bot"></span> IU known bot
          · Click any dot or list row to filter posts.
        </p>
      </div>
    </details>
  `;
}

export function priorityScatterPanelHtml(
  criticalCount: number,
  edgeCount: number,
  outrageDiag: OutrageDiagnostics
): string {
  const noSpread = edgeCount === 0;
  const yCompressed = outrageDiag.compressed;
  const badgeLabel =
    noSpread && yCompressed
      ? "relative targets"
      : noSpread || yCompressed
        ? "high outrage only"
        : "critical targets";
  return `
    <section class="panel panel-chart-wide priority-panel" id="priority-scatter-panel">
      <h2>Author prioritization
        <span class="topology-badge ${noSpread || yCompressed ? "topology-isolated" : "topology-star"}">${criticalCount} ${badgeLabel}</span>
      </h2>
      ${priorityExplainerHtml(edgeCount, outrageDiag)}
      ${noSpreadNoticeHtml(edgeCount)}
      ${scatterOutrageFloorNoticeHtml(outrageDiag)}
      <p class="chart-caption">
        ${noSpread ? "All authors at X = 0 until propagation edges exist." : "Top-right = highest spread and outrage."}
        ${yCompressed && !noSpread ? ` Y-axis zoomed — max outrage ${outrageDiag.maxAuthorOutrage.toFixed(2)}.` : ""}
      </p>
      <div class="chart-wrap chart-wrap-scatter">
        <canvas id="priority-scatter-chart" aria-label="Author prioritization scatter plot"></canvas>
      </div>
      <h3 class="priority-target-list-heading">Flagged accounts</h3>
      <p class="chart-caption priority-target-list-caption">Sorted by spread × outrage when both axes have signal; otherwise by relative outrage tier.</p>
      <ul class="priority-target-list" id="priority-target-list"></ul>
    </section>
  `;
}

export function renderPriorityTargetList(
  listEl: HTMLElement,
  points: AuthorPriorityPoint[],
  onAuthorSelect?: (point: AuthorPriorityPoint) => void,
  edgeCount = 0,
  outrageDiag?: OutrageDiagnostics
): void {
  const critical = points
    .filter((p) => p.critical)
    .sort((a, b) => b.x * b.y - a.x * a.y);

  if (critical.length === 0) {
    let msg = "No authors in the critical quadrant for this narrative.";
    if (outrageDiag?.compressed && edgeCount === 0) {
      msg =
        "No relative targets in this compressed snapshot (X=0, outrage ≤ 0.15). Volume may be high while lexicon scores stay neutral—see Sentiment shift and theme/duplicate panels.";
    } else if (outrageDiag?.compressed) {
      msg =
        "No authors above the relative outrage tier—lexicon scores are floored near zero for this narrative.";
    } else if (edgeCount === 0) {
      msg =
        "No high-outrage targets flagged. Propagation graph has no edges, so spread (X) is zero for everyone—see diagnosis above.";
    }
    listEl.innerHTML = `<li class='empty'>${msg}</li>`;
    return;
  }

  listEl.innerHTML = critical
    .slice(0, 12)
    .map(
      (p) =>
        `<li class="priority-target-item${p.known_bot ? " priority-known-bot" : ""}" data-author-id="${p.author_id}" role="button" tabindex="0" aria-label="Investigate ${p.label}, ${p.post_count} posts">
          <strong>${p.label}</strong>
          <span>out ${p.x} · outrage ${p.y.toFixed(3)} · ${p.post_count} posts</span>
          ${p.known_bot ? '<span class="bot-pill">IU known bot</span>' : ""}
          <span class="cluster-cta">View ${p.post_count} posts →</span>
        </li>`
    )
    .join("");

  if (!onAuthorSelect) return;

  listEl.querySelectorAll<HTMLElement>(".priority-target-item").forEach((el) => {
    const authorId = el.dataset.authorId;
    const point = critical.find((p) => p.author_id === authorId);
    if (!point) return;
    const run = () => onAuthorSelect(point);
    el.addEventListener("click", run);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        run();
      }
    });
  });
}

export function mountPrioritizationScatter(
  canvas: HTMLCanvasElement,
  points: AuthorPriorityPoint[],
  onAuthorSelect?: (point: AuthorPriorityPoint) => void,
  edgeCount = 0,
  outrageDiag?: OutrageDiagnostics
): { xMid: number; yMid: number } {
  const noSpread = edgeCount === 0;
  const yCompressed = outrageDiag?.compressed ?? false;
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  const parent = canvas.parentElement;
  if (points.length === 0) {
    if (parent) {
      parent.innerHTML = stateEmptyHtml("No authors to plot");
    }
    return { xMid: 0, yMid: 0 };
  }

  const xValues = points.map((p) => p.x);
  const yValues = points.map((p) => p.y);
  const xMid = median(xValues);
  const yMid = median(yValues);
  const yGuide = yCompressed ? yPercentile75(points) : yMid;
  const xHasSpread = hasSpread(xValues);
  const yHasSpread = hasSpread(yValues);
  const showVerticalQuadrant = !noSpread && xHasSpread && xMid > 0;
  const showHorizontalQuadrant =
    yHasSpread && yGuide > 0 && (yCompressed || yMid > 0);
  const maxX = noSpread ? 1 : Math.max(1, ...xValues);
  const maxY = Math.max(...yValues, 0);
  const yAxisMax = yCompressed
    ? Math.max(0.2, maxY + 0.04)
    : 1;

  const bots = points.filter((p) => p.known_bot);
  const criticalOther = points.filter((p) => p.critical && !p.known_bot);
  const rest = points.filter((p) => !p.known_bot && !p.critical);
  scatterPools = [rest, criticalOther, bots];

  const config: ChartConfiguration<"scatter"> = {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Authors",
          data: rest.map((p) => ({ x: p.x, y: p.y })),
          pointBackgroundColor: COLORS.author,
          pointRadius: 5,
          pointHoverRadius: 7,
        },
        {
          label: yCompressed
            ? "Top tier (lexicon floor)"
            : noSpread
              ? "High outrage (no spread data)"
              : "Critical (high spread + outrage)",
          data: criticalOther.map((p) => ({ x: p.x, y: p.y })),
          pointBackgroundColor: COLORS.critical,
          pointBorderColor: COLORS.criticalBorder,
          pointBorderWidth: 2,
          pointRadius: 7,
          pointHoverRadius: 9,
        },
        {
          label: "IU known bot",
          data: bots.map((p) => ({ x: p.x, y: p.y })),
          pointBackgroundColor: COLORS.bot,
          pointBorderColor: COLORS.botBorder,
          pointBorderWidth: 2,
          pointRadius: 9,
          pointHoverRadius: 11,
          pointStyle: "rectRot",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (_event, elements) => {
        if (!elements.length || !onAuthorSelect) return;
        const el = elements[0];
        const pool = scatterPools[el.datasetIndex];
        const point = pool?.[el.index];
        if (point) onAuthorSelect(point);
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: { color: COLORS.text, boxWidth: 10, padding: 12 },
        },
        tooltip: {
          backgroundColor: "#161f2b",
          borderColor: COLORS.grid,
          borderWidth: 1,
          titleColor: "#e8edf4",
          bodyColor: COLORS.text,
          callbacks: {
            title: (items) => {
              const idx = items[0]?.dataIndex ?? 0;
              const pool =
                items[0]?.datasetIndex === 2
                  ? bots
                  : items[0]?.datasetIndex === 1
                    ? criticalOther
                    : rest;
              return pool[idx]?.label ?? "";
            },
            label: (item) => {
              const pool =
                item.datasetIndex === 2
                  ? bots
                  : item.datasetIndex === 1
                    ? criticalOther
                    : rest;
              const p = pool[item.dataIndex];
              if (!p) return "";
              return [
                `Out-degree: ${p.x}${noSpread ? " (no propagation edges in ingest)" : ""}`,
                `Max outrage: ${p.y.toFixed(3)}`,
                `Posts: ${p.post_count}`,
                p.known_bot ? "IU astroturf registry" : "",
                p.critical
                  ? yCompressed
                    ? "Top tier on lexicon floor"
                    : noSpread
                      ? "High outrage (X=0 wall)"
                      : "Critical quadrant"
                  : "",
              ].filter(Boolean);
            },
          },
        },
      },
      scales: {
        x: {
          min: 0,
          max: maxX + 0.5,
          title: {
            display: true,
            text: noSpread
              ? "Out-degree (spread) — all zero: no edges"
              : "Out-degree (spread)",
            color: COLORS.text,
          },
          ticks: { color: COLORS.text, stepSize: 1 },
          grid: { color: COLORS.gridSubtle },
        },
        y: {
          min: 0,
          max: yAxisMax,
          title: {
            display: true,
            text: yCompressed
              ? `Max outrage (zoomed: ≤ ${OUTRAGE_COMPRESSION_THRESHOLD})`
              : "Max outrage index",
            color: COLORS.text,
          },
          ticks: {
            color: COLORS.text,
            callback: (v) => Number(v).toFixed(2),
          },
          grid: { color: COLORS.grid },
        },
      },
    },
    plugins: [
      {
        id: "quadrantGuide",
        afterDraw(chart) {
          const { ctx, chartArea, scales } = chart;
          if (!chartArea) return;

          const xPx = showVerticalQuadrant
            ? scales.x.getPixelForValue(xMid)
            : chartArea.left;
          const yPx = showHorizontalQuadrant
            ? scales.y.getPixelForValue(yGuide)
            : chartArea.bottom;

          ctx.save();
          ctx.strokeStyle = COLORS.quadrant;
          ctx.lineWidth = 1;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          if (showVerticalQuadrant) {
            ctx.moveTo(xPx, chartArea.top);
            ctx.lineTo(xPx, chartArea.bottom);
          }
          if (showHorizontalQuadrant) {
            ctx.moveTo(chartArea.left, yPx);
            ctx.lineTo(chartArea.right, yPx);
          }
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = "rgba(245, 166, 35, 0.85)";
          ctx.font = "600 10px IBM Plex Sans, sans-serif";
          if (showVerticalQuadrant && showHorizontalQuadrant) {
            const labelX = xPx + (chartArea.right - xPx) / 2 - 30;
            const labelY = chartArea.top + 14;
            ctx.fillText(yCompressed ? "TOP TIER" : "CRITICAL", labelX, labelY);
          } else if (noSpread && yCompressed && showHorizontalQuadrant) {
            ctx.fillText("TOP TIER", chartArea.right - 58, chartArea.top + 14);
          }

          if (noSpread) {
            const x0 = scales.x.getPixelForValue(0);
            ctx.strokeStyle = "rgba(192, 57, 43, 0.55)";
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 3]);
            ctx.beginPath();
            ctx.moveTo(x0, chartArea.top);
            ctx.lineTo(x0, chartArea.bottom);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = "rgba(192, 57, 43, 0.9)";
            ctx.font = "600 10px IBM Plex Sans, sans-serif";
            ctx.save();
            ctx.translate(x0 + 6, chartArea.top + 48);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText("X = 0 wall", 0, 0);
            ctx.restore();
          }

          if (yCompressed) {
            const yFloor = scales.y.getPixelForValue(
              OUTRAGE_COMPRESSION_THRESHOLD
            );
            if (yFloor <= chartArea.bottom && yFloor >= chartArea.top) {
              ctx.strokeStyle = "rgba(245, 166, 35, 0.45)";
              ctx.lineWidth = 1;
              ctx.setLineDash([5, 4]);
              ctx.beginPath();
              ctx.moveTo(chartArea.left, yFloor);
              ctx.lineTo(chartArea.right, yFloor);
              ctx.stroke();
              ctx.setLineDash([]);
            }
            ctx.fillStyle = "rgba(245, 166, 35, 0.9)";
            ctx.font = "600 10px IBM Plex Sans, sans-serif";
            ctx.fillText(
              `Y ≤ ${OUTRAGE_COMPRESSION_THRESHOLD} floor`,
              chartArea.left + 4,
              chartArea.bottom - 6
            );
          }
          ctx.restore();
        },
      },
    ],
  };

  activeChart = new Chart(canvas, config);
  return { xMid, yMid };
}

export function destroyPrioritizationScatter(): void {
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }
}

import {
  Chart,
  Legend,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  type ChartConfiguration,
} from "chart.js";

import type { CibReport, GraphAuthor, Post, PropagationGraph } from "./types";

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

export function buildAuthorPriorityPoints(
  graph: PropagationGraph,
  cib: CibReport,
  posts: Post[]
): AuthorPriorityPoint[] {
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

  return raw.map((p) => ({
    ...p,
    critical: p.x >= xMid && p.y >= yMid && (p.x > 0 || p.y >= 0.25),
  }));
}

export function priorityScatterPanelHtml(criticalCount: number): string {
  return `
    <section class="panel panel-chart-wide priority-panel">
      <h2>Author prioritization
        <span class="topology-badge topology-star">${criticalCount} critical targets</span>
      </h2>
      <p class="chart-caption">
        X: out-degree (spread). Y: max outrage. Bright red = IU astroturf known bot.
        Top-right quadrant = operational mitigation priority.
      </p>
      <div class="chart-wrap chart-wrap-scatter">
        <canvas id="priority-scatter-chart" aria-label="Author prioritization scatter plot"></canvas>
      </div>
      <ul class="priority-target-list" id="priority-target-list"></ul>
    </section>
  `;
}

export function renderPriorityTargetList(
  listEl: HTMLElement,
  points: AuthorPriorityPoint[]
): void {
  const critical = points
    .filter((p) => p.critical)
    .sort((a, b) => b.x * b.y - a.x * a.y);

  if (critical.length === 0) {
    listEl.innerHTML = "<li class='empty'>No authors in the critical quadrant for this narrative.</li>";
    return;
  }

  listEl.innerHTML = critical
    .slice(0, 12)
    .map(
      (p) =>
        `<li class="${p.known_bot ? "priority-known-bot" : ""}">
          <strong>${p.label}</strong>
          <span>out ${p.x} · outrage ${p.y.toFixed(3)} · ${p.post_count} posts</span>
          ${p.known_bot ? '<span class="bot-pill">IU known bot</span>' : ""}
        </li>`
    )
    .join("");
}

export function mountPrioritizationScatter(
  canvas: HTMLCanvasElement,
  points: AuthorPriorityPoint[]
): { xMid: number; yMid: number } {
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  const parent = canvas.parentElement;
  if (points.length === 0) {
    if (parent) {
      parent.innerHTML = "<p class='loading'>No authors to plot.</p>";
    }
    return { xMid: 0, yMid: 0 };
  }

  const xMid = median(points.map((p) => p.x));
  const yMid = median(points.map((p) => p.y));
  const maxX = Math.max(1, ...points.map((p) => p.x));

  const bots = points.filter((p) => p.known_bot);
  const criticalOther = points.filter((p) => p.critical && !p.known_bot);
  const rest = points.filter((p) => !p.known_bot && !p.critical);

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
          label: "Critical (high spread + outrage)",
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
                `Out-degree: ${p.x}`,
                `Max outrage: ${p.y.toFixed(3)}`,
                `Posts: ${p.post_count}`,
                p.known_bot ? "IU astroturf registry" : "",
                p.critical ? "Critical quadrant" : "",
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
            text: "Out-degree (spread)",
            color: COLORS.text,
          },
          ticks: { color: COLORS.text, stepSize: 1 },
          grid: { color: COLORS.gridSubtle },
        },
        y: {
          min: 0,
          max: 1,
          title: {
            display: true,
            text: "Max outrage index",
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

          const xPx = scales.x.getPixelForValue(xMid);
          const yPx = scales.y.getPixelForValue(yMid);

          ctx.save();
          ctx.strokeStyle = COLORS.quadrant;
          ctx.lineWidth = 1;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(xPx, chartArea.top);
          ctx.lineTo(xPx, chartArea.bottom);
          ctx.moveTo(chartArea.left, yPx);
          ctx.lineTo(chartArea.right, yPx);
          ctx.stroke();
          ctx.setLineDash([]);

          ctx.fillStyle = "rgba(245, 166, 35, 0.85)";
          ctx.font = "600 10px IBM Plex Sans, sans-serif";
          ctx.fillText("CRITICAL", chartArea.right - 52, yPx - 6);
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

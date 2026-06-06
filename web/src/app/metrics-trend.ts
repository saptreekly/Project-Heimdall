import Chart from "chart.js/auto";
import { escapeHtml } from "../post-display";
import type { MetricsHistoryEntry } from "../types";

export function metricsTrendPanelHtml(entries: MetricsHistoryEntry[], narrativeName: string): string {
  if (!entries.length) {
    return `
      <section class="panel panel-metrics-trend">
        <h2>Volume trend</h2>
        <p class="chart-caption empty">No metrics history yet — populated after Pages deploy runs snapshot_report.</p>
      </section>
    `;
  }
  return `
    <section class="panel panel-metrics-trend">
      <h2>Volume trend</h2>
      <p class="chart-caption">Daily snapshot metrics for <strong>${escapeHtml(narrativeName)}</strong> (last ${entries.length} days).</p>
      <canvas id="metrics-trend-chart" aria-label="Post volume trend chart" height="120"></canvas>
    </section>
  `;
}

export function mountMetricsTrendChart(
  canvas: HTMLCanvasElement,
  entries: MetricsHistoryEntry[],
  narrativeName: string
): void {
  const rows = entries
    .map((e) => {
      const row = (e.narratives ?? []).find((n) => n.name === narrativeName);
      return {
        day: (e.generated_at ?? "").slice(0, 10),
        posts: row?.posts_in_snapshot ?? e.total_posts_in_snapshot ?? 0,
        coordination: row?.combined_suspicion ?? null,
      };
    })
    .filter((r) => r.day);

  if (!rows.length) return;

  const existing = Chart.getChart(canvas);
  existing?.destroy();

  new Chart(canvas, {
    type: "line",
    data: {
      labels: rows.map((r) => r.day),
      datasets: [
        {
          label: "Posts in snapshot",
          data: rows.map((r) => r.posts),
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.12)",
          fill: true,
          tension: 0.25,
          yAxisID: "y",
        },
        {
          label: "Combined suspicion",
          data: rows.map((r) => r.coordination),
          borderColor: "#db2777",
          borderDash: [4, 4],
          tension: 0.25,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { beginAtZero: true, position: "left", title: { display: true, text: "Posts" } },
        y1: {
          beginAtZero: true,
          position: "right",
          grid: { drawOnChartArea: false },
          max: 1,
          title: { display: true, text: "Suspicion" },
        },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

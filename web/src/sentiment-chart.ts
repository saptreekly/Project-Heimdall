import {
  sentimentOutrageNoticeHtml,
  type OutrageDiagnostics,
} from "./outrage-diagnostics";
import { stateEmptyHtml } from "./ui-states";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
} from "chart.js";

Chart.register(
  LineController,
  BarController,
  LineElement,
  BarElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  Filler
);

export interface SentimentBucket {
  date: string;
  mean_outrage: number;
  count: number;
  mean_negativity?: number;
  mean_ragebait?: number;
  mean_stance?: number;
  mean_dehumanization?: number;
  mean_anti_authority?: number;
  tier_counts?: Record<string, number>;
  polarity_counts?: Record<string, number>;
  volume_outrage_divergence?: boolean;
}

let activeChart: Chart | null = null;
let activeTierChart: Chart | null = null;

const COLORS = {
  text: "#8b9cb3",
  grid: "#2a384c",
  gridSubtle: "#1f2a3a",
  outrage: "#c0392b",
  outrageFill: "rgba(192, 57, 43, 0.12)",
  volume: "rgba(138, 155, 179, 0.5)",
  volumeBorder: "rgba(138, 155, 179, 0.85)",
  tierNeutral: "rgba(138, 155, 179, 0.55)",
  tierEscalating: "rgba(230, 126, 34, 0.75)",
  tierHighConflict: "rgba(192, 57, 43, 0.85)",
  tierEmerging: "rgba(155, 89, 182, 0.75)",
};

const TIER_ORDER = [
  "neutral",
  "escalating",
  "high_conflict",
  "emerging_theme",
] as const;

export function sentimentChartPanelHtml(
  trend: string,
  outrageDiag: OutrageDiagnostics,
  wowAlert?: string | null
): string {
  const wowLine = wowAlert
    ? `<p class="chart-caption sentiment-wow-alert">Week-over-week: ${escapeHtml(wowAlert.replace(/_/g, " "))}</p>`
    : "";
  return `
    <section class="panel panel-chart-wide" id="sentiment-chart-panel">
      <h2>Sentiment shift <span class="trend-pill">${trend}</span></h2>
      ${sentimentOutrageNoticeHtml(outrageDiag)}
      <p class="chart-caption">
        Line: daily mean outrage (left axis). Bars: post volume that day (right axis).
        ${outrageDiag.compressed ? "High bar + flat red line = volume without lexicon outrage signal." : ""}
        Click a day to filter posts below.
      </p>
      ${wowLine}
      <div class="chart-wrap">
        <canvas id="sentiment-timeline-chart" aria-label="Daily mean outrage and post volume"></canvas>
      </div>
      <p class="chart-caption chart-caption-sub">Stacked area: escalation tier mix per day (share of posts).</p>
      <div class="chart-wrap chart-wrap-compact">
        <canvas id="sentiment-tier-chart" aria-label="Daily escalation tier mix"></canvas>
      </div>
    </section>
  `;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function tierShare(bucket: SentimentBucket, tier: string): number {
  const counts = bucket.tier_counts;
  if (!counts) return 0;
  const total = TIER_ORDER.reduce((sum, key) => sum + (counts[key] ?? 0), 0);
  if (total === 0) return 0;
  return ((counts[tier] ?? 0) / total) * 100;
}

export function mountSentimentChart(
  canvas: HTMLCanvasElement,
  buckets: SentimentBucket[],
  onDateSelect?: (date: string) => void,
  outrageDiag?: OutrageDiagnostics
): void {
  const yCompressed = outrageDiag?.compressed ?? false;
  const maxMean = Math.max(...buckets.map((b) => b.mean_outrage), 0);
  const outrageAxisMax = yCompressed
    ? Math.max(0.2, maxMean + 0.05)
    : 1;
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  if (buckets.length === 0) {
    const parent = canvas.parentElement;
    if (parent) {
      parent.innerHTML = stateEmptyHtml(
        "Not enough dated posts for a timeline",
        "Posts need valid posted_at timestamps."
      );
    }
    return;
  }

  const labels = buckets.map((b) => b.date);
  const config: ChartConfiguration = {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Posts per day",
          data: buckets.map((b) => b.count),
          yAxisID: "yVolume",
          backgroundColor: buckets.map((b) =>
            b.volume_outrage_divergence
              ? "rgba(241, 196, 15, 0.55)"
              : COLORS.volume
          ),
          borderColor: buckets.map((b) =>
            b.volume_outrage_divergence
              ? "rgba(241, 196, 15, 0.9)"
              : COLORS.volumeBorder
          ),
          borderWidth: 1,
          borderRadius: 3,
          order: 2,
        },
        {
          type: "line",
          label: "Mean outrage",
          data: buckets.map((b) => b.mean_outrage),
          yAxisID: "yOutrage",
          borderColor: COLORS.outrage,
          backgroundColor: COLORS.outrageFill,
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: COLORS.outrage,
          borderWidth: 2.5,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      onClick: (_event, elements) => {
        if (!elements.length || !onDateSelect) return;
        const idx = elements[0].index;
        const date = buckets[idx]?.date;
        if (date) onDateSelect(date);
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: { color: COLORS.text, boxWidth: 12, padding: 14 },
        },
        tooltip: {
          backgroundColor: "#161f2b",
          borderColor: COLORS.grid,
          borderWidth: 1,
          titleColor: "#e8edf4",
          bodyColor: COLORS.text,
          filter: (item) => item.datasetIndex === 1,
          callbacks: {
            label: (item) => {
              const idx = item.dataIndex;
              const b = buckets[idx];
              const lines = [
                `Mean outrage: ${b.mean_outrage.toFixed(3)}`,
                `Posts: ${b.count}`,
              ];
              if (b.mean_dehumanization != null) {
                lines.push(`Dehumanization: ${b.mean_dehumanization.toFixed(3)}`);
              }
              if (b.volume_outrage_divergence) {
                lines.push("Volume–outrage divergence");
              }
              return lines;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: COLORS.text, maxRotation: 45, minRotation: 0 },
          grid: { color: COLORS.gridSubtle },
        },
        yOutrage: {
          type: "linear",
          position: "left",
          min: 0,
          max: outrageAxisMax,
          title: {
            display: true,
            text: yCompressed
              ? "Mean outrage (zoomed: lexicon floor)"
              : "Mean outrage",
            color: COLORS.text,
            font: { size: 11 },
          },
          ticks: {
            color: COLORS.text,
            callback: (v) => Number(v).toFixed(2),
          },
          grid: { color: COLORS.grid },
        },
        yVolume: {
          type: "linear",
          position: "right",
          beginAtZero: true,
          title: {
            display: true,
            text: "Post volume",
            color: COLORS.text,
            font: { size: 11 },
          },
          ticks: {
            color: COLORS.text,
            precision: 0,
          },
          grid: { drawOnChartArea: false },
        },
      },
    },
  };

  activeChart = new Chart(canvas, config);
}

export function mountSentimentTierChart(
  canvas: HTMLCanvasElement,
  buckets: SentimentBucket[]
): void {
  if (activeTierChart) {
    activeTierChart.destroy();
    activeTierChart = null;
  }
  if (buckets.length === 0 || !buckets.some((b) => b.tier_counts)) {
    const parent = canvas.parentElement;
    if (parent) parent.hidden = true;
    return;
  }

  const labels = buckets.map((b) => b.date);
  const tierColors: Record<string, string> = {
    neutral: COLORS.tierNeutral,
    escalating: COLORS.tierEscalating,
    high_conflict: COLORS.tierHighConflict,
    emerging_theme: COLORS.tierEmerging,
  };
  const tierLabels: Record<string, string> = {
    neutral: "Neutral",
    escalating: "Escalating",
    high_conflict: "High conflict",
    emerging_theme: "Emerging theme",
  };

  activeTierChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: TIER_ORDER.map((tier) => ({
        label: tierLabels[tier],
        data: buckets.map((b) => tierShare(b, tier)),
        borderColor: tierColors[tier],
        backgroundColor: tierColors[tier],
        fill: true,
        stack: "tiers",
        tension: 0.25,
        pointRadius: 0,
        borderWidth: 1,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: { color: COLORS.text, boxWidth: 10, padding: 10 },
        },
        tooltip: {
          callbacks: {
            label: (item) =>
              `${item.dataset.label}: ${Number(item.raw).toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: COLORS.text, maxRotation: 45 },
          grid: { color: COLORS.gridSubtle },
        },
        y: {
          stacked: true,
          min: 0,
          max: 100,
          ticks: {
            color: COLORS.text,
            callback: (v) => `${v}%`,
          },
          grid: { color: COLORS.grid },
        },
      },
    },
  });
}

export function destroySentimentChart(): void {
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }
  if (activeTierChart) {
    activeTierChart.destroy();
    activeTierChart = null;
  }
}

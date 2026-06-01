import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
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
  Tooltip
);

export interface SentimentBucket {
  date: string;
  mean_outrage: number;
  count: number;
}

let activeChart: Chart | null = null;

const COLORS = {
  text: "#8b9cb3",
  grid: "#2a384c",
  gridSubtle: "#1f2a3a",
  outrage: "#c0392b",
  outrageFill: "rgba(192, 57, 43, 0.12)",
  volume: "rgba(138, 155, 179, 0.5)",
  volumeBorder: "rgba(138, 155, 179, 0.85)",
};

export function sentimentChartPanelHtml(trend: string): string {
  return `
    <section class="panel panel-chart-wide">
      <h2>Sentiment shift <span class="trend-pill">${trend}</span></h2>
      <p class="chart-caption">
        Line: daily mean outrage (left axis). Bars: post volume that day (right axis).
        Click a day to filter posts below.
      </p>
      <div class="chart-wrap">
        <canvas id="sentiment-timeline-chart" aria-label="Daily mean outrage and post volume"></canvas>
      </div>
    </section>
  `;
}

export function mountSentimentChart(
  canvas: HTMLCanvasElement,
  buckets: SentimentBucket[],
  onDateSelect?: (date: string) => void
): void {
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }

  if (buckets.length === 0) {
    const parent = canvas.parentElement;
    if (parent) {
      parent.innerHTML =
        "<p class='loading'>Not enough dated posts for a timeline.</p>";
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
          backgroundColor: COLORS.volume,
          borderColor: COLORS.volumeBorder,
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
              return [
                `Mean outrage: ${b.mean_outrage.toFixed(3)}`,
                `Posts: ${b.count}`,
              ];
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
          max: 1,
          title: {
            display: true,
            text: "Mean outrage",
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

export function destroySentimentChart(): void {
  if (activeChart) {
    activeChart.destroy();
    activeChart = null;
  }
}

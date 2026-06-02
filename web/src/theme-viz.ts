import type { Post, ThemeCluster, ThemesReport } from "./types";
import { escapeHtml, labelList, safeText } from "./safe-text";
import {
  activeBrushClusterIds,
  brushOpacity,
  onThemeBrushChange,
  setThemeBrushHover,
  setThemeBrushSelection,
} from "./theme-brush";
import {
  BarController,
  BarElement,
  BubbleController,
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
  BubbleController,
  LineElement,
  BarElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip
);

export interface ThemeTimelineVizEntry {
  cluster_id: number;
  label_terms?: string[];
  label_phrases?: string[];
  label_distinctiveness?: number;
  emerging_theme: boolean;
  quality_score?: number;
  author_entropy?: number;
  is_noise?: boolean;
  size: number;
  first_seen: string | null;
  last_seen: string | null;
  daily_counts?: Record<string, number>;
  post_ids?: number[];
}

let activeStream: Chart | null = null;
let activeScatter: Chart | null = null;
let activeTier: Chart | null = null;
let streamClusterIds: number[] = [];
let scatterClusterIds: number[] = [];
let tierClusterIds: number[] = [];
let tierDatasetBaseColors: string[] = [];
let sankeyHostRef: HTMLElement | null = null;
let brushUnsub: (() => void) | null = null;
let onClusterClick: ((clusterId: number, label: string, postIds: number[]) => void) | null = null;

const PALETTE = [
  "#3498db",
  "#e74c3c",
  "#2ecc71",
  "#9b59b6",
  "#f39c12",
  "#1abc9c",
  "#e67e22",
  "#34495e",
];

const TIER_COLORS: Record<string, string> = {
  neutral: "rgba(138, 155, 179, 0.65)",
  escalating: "rgba(230, 126, 34, 0.8)",
  inflammatory: "rgba(192, 57, 43, 0.85)",
  unknown: "rgba(100, 116, 139, 0.5)",
};

const MAX_STREAM_THEMES = 6;
const MAX_STREAM_DATES = 60;

export function clusterLabel(entry: ThemeTimelineVizEntry | ThemeCluster): string {
  const phrases = labelList(entry.label_phrases);
  if (phrases.length > 0) return phrases[0];
  const terms = labelList(entry.label_terms);
  if (terms.length > 0) return terms[0];
  return `cluster ${entry.cluster_id}`;
}

function paletteColor(index: number, alpha = 1): string {
  const hex = PALETTE[index % PALETTE.length];
  if (alpha >= 1) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function withAlpha(rgba: string, alpha: number): string {
  if (alpha >= 1) return rgba;
  const match = rgba.match(/rgba?\(([^)]+)\)/);
  if (!match) return rgba;
  const parts = match[1].split(",").map((p) => p.trim());
  if (parts.length < 3) return rgba;
  return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
}

function sampleDates(dates: string[], max: number): string[] {
  if (dates.length <= max) return dates;
  const step = Math.ceil(dates.length / max);
  return dates.filter((_, idx) => idx % step === 0 || idx === dates.length - 1);
}

function allDates(timeline: ThemeTimelineVizEntry[]): string[] {
  const set = new Set<string>();
  for (const entry of timeline) {
    for (const day of Object.keys(entry.daily_counts ?? {})) {
      set.add(day);
    }
  }
  return sampleDates([...set].sort(), MAX_STREAM_DATES);
}

function applySankeyBrush(host: HTMLElement | null): void {
  if (!host) return;
  const active = activeBrushClusterIds();
  host.querySelectorAll<SVGElement>(".theme-sankey-link").forEach((el) => {
    const clusterId = parseInt(el.dataset.themeClusterId ?? "", 10);
    if (!Number.isFinite(clusterId)) return;
    el.style.opacity = String(active ? brushOpacity(clusterId) : 0.75);
  });
  host.querySelectorAll<SVGElement>(".theme-sankey-node").forEach((el) => {
    const clusterId = parseInt(el.dataset.themeClusterId ?? "", 10);
    if (!Number.isFinite(clusterId)) return;
    el.style.opacity = String(active ? brushOpacity(clusterId) : 1);
  });
}

function applyChartBrush(): void {
  const active = activeBrushClusterIds();

  if (activeStream && streamClusterIds.length) {
    activeStream.data.datasets.forEach((dataset, idx) => {
      const clusterId = streamClusterIds[idx];
      const opacity = active && clusterId != null ? brushOpacity(clusterId) : 1;
      const color = paletteColor(idx, opacity);
      dataset.borderColor = color;
      dataset.backgroundColor = paletteColor(idx, opacity * 0.35);
    });
    activeStream.update("none");
  }

  if (activeScatter && scatterClusterIds.length) {
    activeScatter.data.datasets[0].backgroundColor = scatterClusterIds.map((clusterId, idx) => {
      const opacity = active ? brushOpacity(clusterId) : 1;
      return paletteColor(idx, opacity * 0.75);
    });
    activeScatter.update("none");
  }

  if (activeTier && tierClusterIds.length) {
    activeTier.data.datasets.forEach((dataset, di) => {
      const base = tierDatasetBaseColors[di] ?? TIER_COLORS.unknown;
      dataset.backgroundColor = tierClusterIds.map((clusterId) => {
        const opacity = active ? brushOpacity(clusterId) : 1;
        return withAlpha(base, opacity);
      });
    });
    activeTier.update("none");
  }

  document.querySelectorAll<HTMLElement>("[data-theme-cluster-id]").forEach((el) => {
    const clusterId = parseInt(el.dataset.themeClusterId ?? "", 10);
    if (!Number.isFinite(clusterId)) return;
    el.style.opacity = String(active ? brushOpacity(clusterId) : 1);
  });

  applySankeyBrush(sankeyHostRef);
}

function ensureBrushListener(): void {
  if (brushUnsub) return;
  brushUnsub = onThemeBrushChange(() => applyChartBrush());
}

export function renderThemeGantt(
  host: HTMLElement,
  timeline: ThemeTimelineVizEntry[],
  onSelect?: (clusterId: number, label: string, postIds: number[]) => void
): void {
  const dated = timeline.filter((t) => t.first_seen && t.last_seen);
  if (dated.length === 0) {
    host.innerHTML = "";
    return;
  }

  const minDate = dated.reduce((m, t) => (t.first_seen! < m ? t.first_seen! : m), dated[0].first_seen!);
  const maxDate = dated.reduce((m, t) => (t.last_seen! > m ? t.last_seen! : m), dated[0].last_seen!);
  const startMs = new Date(minDate).getTime();
  const endMs = new Date(maxDate).getTime();
  const span = Math.max(endMs - startMs, 86400000);

  host.innerHTML = `<div class="theme-gantt">${dated
    .map((entry, idx) => {
      const left = ((new Date(entry.first_seen!).getTime() - startMs) / span) * 100;
      const width = Math.max(
        4,
        ((new Date(entry.last_seen!).getTime() - new Date(entry.first_seen!).getTime()) / span) * 100 + 2
      );
      const color = PALETTE[idx % PALETTE.length];
      const label = escapeHtml(clusterLabel(entry));
      return `<button
        type="button"
        class="theme-gantt-row theme-gantt-row-btn"
        data-theme-cluster-id="${entry.cluster_id}"
        title="${label}: ${escapeHtml(entry.first_seen)} → ${escapeHtml(entry.last_seen)}"
      >
        <span class="theme-gantt-label">${label}</span>
        <div class="theme-gantt-track">
          <span class="theme-gantt-bar${entry.emerging_theme ? " theme-gantt-bar-emerging" : ""}${entry.is_noise ? " theme-gantt-bar-noise" : ""}" style="left:${left.toFixed(1)}%;width:${width.toFixed(1)}%;background:${color}"></span>
        </div>
      </button>`;
    })
    .join("")}</div>`;

  host.querySelectorAll<HTMLButtonElement>(".theme-gantt-row-btn").forEach((btn) => {
    const clusterId = parseInt(btn.dataset.themeClusterId ?? "", 10);
    const entry = dated.find((t) => t.cluster_id === clusterId);
    if (!entry) return;
    const label = clusterLabel(entry);
    const postIds = entry.post_ids ?? [];

    btn.addEventListener("mouseenter", () => setThemeBrushHover(clusterId));
    btn.addEventListener("mouseleave", () => setThemeBrushHover(null));
    btn.addEventListener("click", () => {
      setThemeBrushSelection(clusterId, postIds, label);
      onSelect?.(clusterId, label, postIds);
      onClusterClick?.(clusterId, label, postIds);
    });
  });
}

export function mountThemeStreamgraph(
  canvas: HTMLCanvasElement,
  timeline: ThemeTimelineVizEntry[]
): void {
  activeStream?.destroy();
  activeStream = null;
  streamClusterIds = [];

  const dates = allDates(timeline);
  if (dates.length === 0) return;

  const entries = timeline
    .filter((t) => !t.is_noise)
    .sort((a, b) => b.size - a.size)
    .slice(0, MAX_STREAM_THEMES);
  streamClusterIds = entries.map((e) => e.cluster_id);

  const datasets = entries.map((entry, idx) => ({
    label: clusterLabel(entry),
    data: dates.map((d) => entry.daily_counts?.[d] ?? 0),
    borderColor: paletteColor(idx),
    backgroundColor: paletteColor(idx, 0.2),
    fill: false,
    tension: 0.3,
    pointRadius: 0,
    borderWidth: 2,
  }));

  const config: ChartConfiguration<"line"> = {
    type: "line",
    data: { labels: dates, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      onClick(_evt, elements) {
        if (!elements.length) return;
        const idx = elements[0].datasetIndex;
        const entry = entries[idx];
        if (!entry) return;
        const label = clusterLabel(entry);
        const postIds = entry.post_ids ?? [];
        setThemeBrushSelection(entry.cluster_id, postIds, label);
        onClusterClick?.(entry.cluster_id, label, postIds);
      },
      plugins: {
        legend: { display: datasets.length <= 5, labels: { color: "#8b9cb3", boxWidth: 10 } },
        tooltip: { mode: "index" },
      },
      scales: {
        x: {
          ticks: { color: "#8b9cb3", maxRotation: 45, autoSkip: true, maxTicksLimit: 12 },
          grid: { color: "#1f2a3a" },
        },
        y: {
          stacked: false,
          ticks: { color: "#8b9cb3" },
          grid: { color: "#2a384c" },
        },
      },
    },
  };

  activeStream = new Chart(canvas, config);
  ensureBrushListener();
  applyChartBrush();
}

export function mountThemeScatter(canvas: HTMLCanvasElement, report: ThemesReport): void {
  activeScatter?.destroy();
  activeScatter = null;
  scatterClusterIds = [];

  const points =
    report.cluster_map?.length
      ? report.cluster_map.map((p) => ({
          ...p,
          label: safeText(p.label, `cluster ${p.cluster_id}`),
        }))
      : report.clusters
          .filter((c) => c.map_x != null && c.map_y != null && !c.is_noise)
          .map((c) => ({
            cluster_id: c.cluster_id,
            x: c.map_x!,
            y: c.map_y!,
            size: c.size,
            label: clusterLabel(c),
            emerging_theme: c.emerging_theme,
            is_noise: c.is_noise,
          }));

  if (points.length === 0) return;
  scatterClusterIds = points.map((p) => p.cluster_id);

  const config: ChartConfiguration<"bubble"> = {
    type: "bubble",
    data: {
      datasets: [
        {
          label: "Themes",
          data: points.map((p) => ({
            x: p.x,
            y: p.y,
            r: Math.max(4, Math.min(18, Math.sqrt(p.size) * 3)),
          })),
          backgroundColor: points.map((_p, i) => paletteColor(i, 0.75)),
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      onClick(_evt, elements) {
        if (!elements.length) return;
        const idx = elements[0].index;
        const point = points[idx];
        const cluster = report.clusters.find((c) => c.cluster_id === point.cluster_id);
        const postIds = cluster?.post_ids ?? [];
        setThemeBrushSelection(point.cluster_id, postIds, point.label);
        onClusterClick?.(point.cluster_id, point.label, postIds);
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(ctx) {
              const p = points[ctx.dataIndex];
              return `${p.label} · ${p.size} posts`;
            },
          },
        },
      },
      scales: {
        x: { display: false },
        y: { display: false },
      },
    },
  };

  activeScatter = new Chart(canvas, config);
  ensureBrushListener();
  applyChartBrush();
}

export function mountThemeEscalationChart(
  canvas: HTMLCanvasElement,
  clusters: ThemeCluster[],
  posts: Post[]
): void {
  activeTier?.destroy();
  activeTier = null;
  tierClusterIds = [];
  tierDatasetBaseColors = [];

  const postMap = new Map(posts.map((p) => [p.id, p]));
  const themes = clusters.filter((c) => !c.is_noise).slice(0, 6);
  if (themes.length === 0) return;
  tierClusterIds = themes.map((c) => c.cluster_id);

  const tiers = ["neutral", "escalating", "inflammatory", "unknown"];
  const labels = themes.map((c) => clusterLabel(c));

  const datasets = tiers.map((tier) => {
    const base = TIER_COLORS[tier] ?? TIER_COLORS.unknown;
    tierDatasetBaseColors.push(base);
    return {
      label: tier,
      data: themes.map((cluster) => {
        let count = 0;
        for (const pid of cluster.post_ids) {
          const post = postMap.get(pid);
          const t = post?.escalation_tier ?? "unknown";
          if (t === tier) count += 1;
        }
        return count;
      }),
      backgroundColor: base,
      stack: "tier",
    };
  });

  const config: ChartConfiguration<"bar"> = {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      onClick(_evt, elements) {
        if (!elements.length) return;
        const idx = elements[0].index;
        const cluster = themes[idx];
        const label = clusterLabel(cluster);
        setThemeBrushSelection(cluster.cluster_id, cluster.post_ids, label);
        onClusterClick?.(cluster.cluster_id, label, cluster.post_ids);
      },
      plugins: {
        legend: { labels: { color: "#8b9cb3", boxWidth: 10 } },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: "#8b9cb3", maxRotation: 35 },
          grid: { display: false },
        },
        y: {
          stacked: true,
          ticks: { color: "#8b9cb3" },
          grid: { color: "#2a384c" },
        },
      },
    },
  };

  activeTier = new Chart(canvas, config);
  ensureBrushListener();
  applyChartBrush();
}

interface SankeyFlow {
  theme: string;
  clusterId: number;
  tier: string;
  count: number;
}

function buildSankeyFlows(clusters: ThemeCluster[], posts: Post[]): SankeyFlow[] {
  const postMap = new Map(posts.map((p) => [p.id, p]));
  const flows: SankeyFlow[] = [];
  for (const cluster of clusters.filter((c) => !c.is_noise).slice(0, 8)) {
    const theme = clusterLabel(cluster);
    const tierCounts = new Map<string, number>();
    for (const pid of cluster.post_ids) {
      const tier = postMap.get(pid)?.escalation_tier ?? "unknown";
      tierCounts.set(tier, (tierCounts.get(tier) ?? 0) + 1);
    }
    for (const [tier, count] of tierCounts) {
      if (count > 0) {
        flows.push({ theme, clusterId: cluster.cluster_id, tier, count });
      }
    }
  }
  return flows;
}

export function renderThemeSankey(
  host: HTMLElement,
  clusters: ThemeCluster[],
  posts: Post[]
): void {
  sankeyHostRef = host;
  const flows = buildSankeyFlows(clusters, posts);
  if (flows.length === 0) {
    host.innerHTML = "<p class='empty'>No escalation flows to chart.</p>";
    return;
  }

  const themes = [...new Set(flows.map((f) => f.theme))];
  const tiers = ["neutral", "escalating", "inflammatory", "unknown"].filter((tier) =>
    flows.some((f) => f.tier === tier)
  );
  const themeTotals = new Map(themes.map((t) => [t, flows.filter((f) => f.theme === t).reduce((s, f) => s + f.count, 0)]));
  const maxTotal = Math.max(...themeTotals.values(), 1);
  const width = 640;
  const height = Math.max(180, themes.length * 28 + tiers.length * 8);
  const leftX = 8;
  const rightX = width - 120;
  const midX = width / 2;

  let yTheme = 12;
  const themeY = new Map<string, number>();
  for (const theme of themes) {
    themeY.set(theme, yTheme);
    yTheme += 28;
  }

  let yTier = 12;
  const tierY = new Map<string, number>();
  for (const tier of tiers) {
    tierY.set(tier, yTier);
    yTier += 24;
  }

  const paths = flows
    .map((flow) => {
      const y0 = themeY.get(flow.theme)! + 10;
      const y1 = tierY.get(flow.tier)! + 10;
      const strokeW = Math.max(2, (flow.count / maxTotal) * 18);
      const color = TIER_COLORS[flow.tier] ?? TIER_COLORS.unknown;
      return `<path
        class="theme-sankey-link"
        data-theme-cluster-id="${flow.clusterId}"
        d="M ${leftX + 100} ${y0} C ${midX} ${y0}, ${midX} ${y1}, ${rightX} ${y1}"
        stroke="${color}"
        stroke-width="${strokeW}"
        fill="none"
        opacity="0.75"
      />`;
    })
    .join("");

  const themeNodes = themes
    .map((theme, idx) => {
      const total = themeTotals.get(theme) ?? 0;
      const clusterId = flows.find((f) => f.theme === theme)?.clusterId ?? -1;
      const barH = Math.max(8, (total / maxTotal) * 20);
      const y = themeY.get(theme)!;
      const label = escapeHtml(theme);
      return `<g class="theme-sankey-node" data-theme-cluster-id="${clusterId}">
        <rect x="${leftX}" y="${y}" width="96" height="${barH}" rx="3" fill="${paletteColor(idx, 0.85)}" />
        <text x="${leftX + 100}" y="${y + barH - 2}" class="theme-sankey-label">${label}</text>
      </g>`;
    })
    .join("");

  const tierNodes = tiers
    .map((tier) => {
      const total = flows.filter((f) => f.tier === tier).reduce((s, f) => s + f.count, 0);
      const barH = Math.max(8, (total / maxTotal) * 20);
      const y = tierY.get(tier)!;
      const color = TIER_COLORS[tier] ?? TIER_COLORS.unknown;
      return `<g class="theme-sankey-tier">
        <rect x="${rightX}" y="${y}" width="96" height="${barH}" rx="3" fill="${color}" />
        <text x="${rightX - 6}" y="${y + barH - 2}" text-anchor="end" class="theme-sankey-label">${escapeHtml(tier)}</text>
      </g>`;
    })
    .join("");

  host.innerHTML = `<svg class="theme-sankey" viewBox="0 0 ${width} ${height}" role="img" aria-label="Theme to escalation Sankey">${paths}${themeNodes}${tierNodes}</svg>`;

  host.querySelectorAll<SVGGElement>(".theme-sankey-node").forEach((node) => {
    const clusterId = parseInt(node.dataset.themeClusterId ?? "", 10);
    if (!Number.isFinite(clusterId)) return;
    const cluster = clusters.find((c) => c.cluster_id === clusterId);
    if (!cluster) return;
    node.style.cursor = "pointer";
    node.addEventListener("mouseenter", () => setThemeBrushHover(clusterId));
    node.addEventListener("mouseleave", () => setThemeBrushHover(null));
    node.addEventListener("click", () => {
      const label = clusterLabel(cluster);
      setThemeBrushSelection(clusterId, cluster.post_ids, label);
      onClusterClick?.(clusterId, label, cluster.post_ids);
    });
  });

  ensureBrushListener();
  applySankeyBrush(host);
}

export function setThemeVizClusterHandler(
  handler: ((clusterId: number, label: string, postIds: number[]) => void) | null
): void {
  onClusterClick = handler;
}

export function destroyThemeViz(): void {
  activeStream?.destroy();
  activeScatter?.destroy();
  activeTier?.destroy();
  activeStream = null;
  activeScatter = null;
  activeTier = null;
  sankeyHostRef = null;
  brushUnsub?.();
  brushUnsub = null;
}

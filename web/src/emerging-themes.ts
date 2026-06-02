import { selectThemeCluster } from "./investigation";
import { escapeHtml, labelList } from "./safe-text";
import type { Post, ThemesReport } from "./types";
import {
  clearThemeBrush,
  setThemeBrushHover,
  setThemeBrushSelection,
} from "./theme-brush";
import {
  AUTO_MERGE_SIM,
  MERGE_DEFAULT_MAX,
  renderMergeDendrogram,
  updateMergeExplorer,
} from "./theme-merge";
import {
  destroyThemeViz,
  mountThemeEscalationChart,
  mountThemeScatter,
  mountThemeStreamgraph,
  renderThemeGantt,
  renderThemeSankey,
  setThemeVizClusterHandler,
} from "./theme-viz";
import { stateLoadingHtml } from "./ui-states";

function displayLabels(entry: {
  label_phrases?: string[];
  label_terms?: string[];
}): string[] {
  const phrases = labelList(entry.label_phrases);
  if (phrases.length > 0) return phrases;
  return labelList(entry.label_terms);
}

function formatTermTokens(terms: string[]): string {
  if (terms.length === 0) return '<span class="theme-token theme-token-empty">(no terms)</span>';
  return terms
    .map((t) => {
      const cls = t.includes(" ") ? "theme-token theme-token-phrase" : "theme-token";
      return `<span class="${cls}">${escapeHtml(t)}</span>`;
    })
    .join("");
}

function cardLabel(terms: string[]): string {
  if (terms.length === 0) return "unnamed cluster";
  return terms.slice(0, 3).join(" · ");
}

let mergeThreshold = MERGE_DEFAULT_MAX;

function postIdsForCluster(
  timeline: Array<{ cluster_id: number; post_ids?: number[] }>,
  clusterId: number
): number[] {
  return timeline.find((t) => t.cluster_id === clusterId)?.post_ids ?? [];
}

function activateClusterSelection(
  clusterId: number,
  label: string,
  postIds: number[],
  mergedClusterIds: number[] | null = null
): void {
  setThemeBrushSelection(clusterId, postIds, label, mergedClusterIds);
  selectThemeCluster(label, postIds);

  document.querySelectorAll(".theme-card").forEach((card) => {
    const id = parseInt((card as HTMLElement).dataset.clusterId ?? "", 10);
    card.classList.toggle("theme-card-active", id === clusterId);
  });
}

export function emergingThemesBadge(report: ThemesReport): string {
  const emerging = report.emerging_theme_count ?? 0;
  const distinct = report.distinct_theme_count ?? report.cluster_count ?? 0;
  if (emerging > 0) {
    return `<span class="topology-badge topology-star">${emerging} emerging</span> <span class="topology-badge topology-sparse">${distinct} distinct</span>`;
  }
  return distinct > 0
    ? `<span class="topology-badge topology-sparse">${distinct} distinct themes</span>`
    : `<span class="topology-badge topology-sparse">embedding clusters</span>`;
}

export function emergingThemesPanelHtml(report: ThemesReport, asInner = false): string {
  const badge = emergingThemesBadge(report);
  const tfidfFallback = (report.model ?? "").toLowerCase().includes("tfidf");
  const fallbackNote = tfidfFallback
    ? `<p class="chart-caption provenance-warn">Lexical TF-IDF fallback — treat emerging labels as low confidence until neural embeddings are enabled on export.</p>`
    : "";
  const inner = `
      <h2 class="themes-panel-title">Emerging themes timeline ${badge}</h2>
      ${fallbackNote}
      <p class="chart-caption">
        PMI-ranked phrase labels with filler filtering. Click any panel — cards, Gantt, map, stream, Sankey, or merge groups —
        to brush-linked highlight across all views and filter posts below.
      </p>
      <div class="themes-layout-grid">
        <div class="themes-layout-main">
          <div id="themes-gantt-host" class="themes-gantt-host"></div>
          <div id="themes-timeline-host" class="themes-timeline-host">
            ${stateLoadingHtml("Loading themes…")}
          </div>
        </div>
        <aside class="themes-layout-side">
          <h3 class="themes-subheading">Merge explorer</h3>
          <div id="theme-merge-host"></div>
          <h3 class="themes-subheading">Merge tree</h3>
          <div id="theme-dendrogram-host" class="theme-dendrogram-host"></div>
        </aside>
      </div>
      <div class="themes-charts-row themes-charts-row-wide">
        <div class="themes-chart-cell themes-chart-cell-wide">
          <h3 class="themes-subheading">Theme → escalation (Sankey)</h3>
          <div id="theme-sankey-host" class="theme-sankey-host"></div>
        </div>
        <div class="themes-chart-cell">
          <h3 class="themes-subheading">Volume stream</h3>
          <canvas id="theme-stream-chart" height="160" aria-label="Theme volume over time"></canvas>
        </div>
        <div class="themes-chart-cell">
          <h3 class="themes-subheading">Theme map</h3>
          <canvas id="theme-scatter-chart" height="160" aria-label="Theme cluster map"></canvas>
        </div>
        <div class="themes-chart-cell">
          <h3 class="themes-subheading">Escalation stack</h3>
          <canvas id="theme-tier-chart" height="160" aria-label="Theme escalation breakdown"></canvas>
        </div>
      </div>
      <p class="metric-sub themes-meta" id="themes-meta"></p>
  `;
  if (asInner) return inner;
  return `
    <section class="panel panel-chart-wide themes-panel" id="emerging-themes-panel">
      ${inner}
    </section>
  `;
}

export function renderEmergingThemesTimeline(
  host: HTMLElement,
  report: ThemesReport,
  posts: Post[] = []
): void {
  destroyThemeViz();
  clearThemeBrush();

  const meta = document.getElementById("themes-meta");
  const ganttHost = document.getElementById("themes-gantt-host");
  const mergeHost = document.getElementById("theme-merge-host");
  const dendrogramHost = document.getElementById("theme-dendrogram-host");
  const sankeyHost = document.getElementById("theme-sankey-host");

  if (mergeHost) delete mergeHost.dataset.mounted;

  setThemeVizClusterHandler((clusterId, label, postIds) => {
    activateClusterSelection(clusterId, label, postIds);
    document.querySelectorAll(".theme-card").forEach((card) => {
      const id = parseInt((card as HTMLElement).dataset.clusterId ?? "", 10);
      card.classList.toggle("theme-card-active", id === clusterId);
    });
  });

  if (!report.available) {
    const hint = report.reason?.includes("USE_EMBEDDING_THEMES")
      ? " Re-export with USE_EMBEDDING_THEMES=true (pip install -e \".[ml]\" on Python 3.11–3.12 for neural embeddings, or base install for TF-IDF fallback)."
      : "";
    host.innerHTML = `<p class="empty">${escapeHtml(report.reason ?? "Theme clustering unavailable in this snapshot.")}${escapeHtml(hint)}</p>`;
    if (ganttHost) ganttHost.innerHTML = "";
    if (mergeHost) mergeHost.innerHTML = "";
    if (dendrogramHost) dendrogramHost.innerHTML = "";
    if (sankeyHost) sankeyHost.innerHTML = "";
    if (meta) meta.textContent = report.method ? `Method: ${report.method}` : "";
    return;
  }

  const timeline = report.timeline?.length
    ? report.timeline
    : report.clusters
        .filter(
          (c) =>
            (c.label_distinctiveness ?? 0) >= 0.12 ||
            c.emerging_theme ||
            c.is_noise
        )
        .map((c) => ({
          cluster_id: c.cluster_id,
          label_terms: c.label_terms,
          label_phrases: c.label_phrases,
          label_distinctiveness: c.label_distinctiveness,
          emerging_theme: c.emerging_theme,
          quality_score: c.quality_score,
          author_entropy: c.author_entropy,
          is_noise: c.is_noise,
          size: c.size,
          first_seen: c.first_seen ?? null,
          last_seen: c.last_seen ?? null,
          daily_counts: c.daily_counts,
          post_ids: c.post_ids,
        }));

  if (timeline.length === 0) {
    host.innerHTML =
      "<p class='empty'>No embedding clusters for this narrative (need ≥3 posts and USE_EMBEDDING_THEMES on export).</p>";
    if (ganttHost) ganttHost.innerHTML = "";
    if (mergeHost) mergeHost.innerHTML = "";
    if (dendrogramHost) dendrogramHost.innerHTML = "";
    if (sankeyHost) sankeyHost.innerHTML = "";
    if (meta) meta.textContent = `Model: ${report.model} · ${report.post_count} posts`;
    return;
  }

  const similarity = report.cluster_similarity ?? [];
  const mergeCandidates = report.merge_candidates ?? [];

  if (mergeHost) {
    updateMergeExplorer(
      mergeHost,
      similarity,
      mergeCandidates,
      timeline,
      mergeThreshold,
      (value) => {
        mergeThreshold = value;
      },
      (group) => {
        const leadId = group.clusterIds[0];
        activateClusterSelection(
          leadId,
          group.label,
          group.postIds,
          group.clusterIds.length > 1 ? group.clusterIds : null
        );
      }
    );
  }

  if (ganttHost) {
    renderThemeGantt(ganttHost, timeline, (clusterId, label, postIds) => {
      activateClusterSelection(clusterId, label, postIds);
    });
  }

  if (dendrogramHost && report.merge_tree?.length) {
    renderMergeDendrogram(dendrogramHost, report.merge_tree);
    dendrogramHost.querySelectorAll<HTMLElement>(".theme-dendrogram-leaf").forEach((leaf) => {
      const clusterId = parseInt(leaf.dataset.clusterId ?? "", 10);
      if (!Number.isFinite(clusterId)) return;
      const entry = timeline.find((t) => t.cluster_id === clusterId);
      if (!entry) return;
      leaf.style.cursor = "pointer";
      leaf.addEventListener("click", () => {
        const label = cardLabel(displayLabels(entry));
        activateClusterSelection(clusterId, label, entry.post_ids ?? []);
      });
    });
  } else if (dendrogramHost) {
    dendrogramHost.innerHTML = `<p class="chart-caption">Merge tree appears when ≥2 clusters export with similarity data.</p>`;
  }

  host.innerHTML = `<div class="themes-timeline">${timeline
    .map((entry) => {
      const terms = displayLabels(entry);
      const label = cardLabel(terms);
      const span =
        entry.first_seen && entry.last_seen
          ? entry.first_seen === entry.last_seen
            ? entry.first_seen
            : `${entry.first_seen} → ${entry.last_seen}`
          : "date unknown";
      const distinctPct =
        entry.label_distinctiveness != null
          ? Math.round(entry.label_distinctiveness * 100)
          : null;
      const qualityPct =
        entry.quality_score != null ? Math.round(entry.quality_score * 100) : null;
      return `<button
        type="button"
        class="theme-card${entry.emerging_theme ? " theme-card-emerging" : ""}${entry.is_noise ? " theme-card-noise" : ""}"
        data-cluster-id="${entry.cluster_id}"
        data-theme-cluster-id="${entry.cluster_id}"
        aria-label="Theme cluster ${escapeHtml(label)}"
      >
        <span class="theme-card-date">${escapeHtml(span)}</span>
        <span class="theme-card-tokens">${formatTermTokens(terms)}</span>
        <span class="theme-card-meta">${entry.size} posts${
          distinctPct != null ? ` · ${distinctPct}% distinct` : ""
        }${qualityPct != null ? ` · ${qualityPct}% quality` : ""}${
          entry.emerging_theme ? " · emerging" : ""
        }${entry.is_noise ? " · unclustered" : ""}</span>
        <span class="cluster-cta">View ${entry.size} posts →</span>
      </button>`;
    })
    .join("")}</div>`;

  host.querySelectorAll<HTMLButtonElement>(".theme-card").forEach((btn) => {
    btn.addEventListener("mouseenter", () => {
      const clusterId = parseInt(btn.dataset.clusterId ?? "", 10);
      if (Number.isFinite(clusterId)) setThemeBrushHover(clusterId);
    });
    btn.addEventListener("mouseleave", () => setThemeBrushHover(null));
    btn.addEventListener("click", () => {
      const clusterId = parseInt(btn.dataset.clusterId ?? "", 10);
      const ids = postIdsForCluster(timeline, clusterId);
      const card = timeline.find((t) => t.cluster_id === clusterId);
      const terms = card ? displayLabels(card) : [];
      const label = terms.length ? `[${terms.join(", ")}]` : `cluster ${clusterId}`;

      host.querySelectorAll(".theme-card").forEach((c) => c.classList.remove("theme-card-active"));
      btn.classList.add("theme-card-active");

      activateClusterSelection(clusterId, label, ids);
      window.dispatchEvent(new CustomEvent("heimdall:goto-posts"));
    });
  });

  const streamCanvas = document.getElementById("theme-stream-chart") as HTMLCanvasElement | null;
  if (streamCanvas) mountThemeStreamgraph(streamCanvas, timeline);

  const scatterCanvas = document.getElementById("theme-scatter-chart") as HTMLCanvasElement | null;
  if (scatterCanvas) mountThemeScatter(scatterCanvas, report);

  const tierCanvas = document.getElementById("theme-tier-chart") as HTMLCanvasElement | null;
  if (tierCanvas) mountThemeEscalationChart(tierCanvas, report.clusters, posts);

  if (sankeyHost) {
    renderThemeSankey(sankeyHost, report.clusters, posts);
  }

  if (meta) {
    const encoder =
      report.model === "tfidf-fallback"
        ? "TF-IDF lexical vectors"
        : report.model;
    const mergeNote = similarity.length
      ? ` · merge slider (auto at ${(AUTO_MERGE_SIM * 100).toFixed(0)}%)`
      : "";
    meta.textContent = `${report.distinct_theme_count ?? report.cluster_count} distinct · ${report.emerging_theme_count} emerging · ${report.method} · ${encoder}${mergeNote}`;
  }
}

export function clearThemeCardSelection(): void {
  document.querySelectorAll(".theme-card-active").forEach((el) => {
    el.classList.remove("theme-card-active");
  });
  clearThemeBrush();
}

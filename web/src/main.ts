import {
  clearSnapshotCache,
  DATA_LINKS,
  fetchAmplification,
  fetchBenchmark,
  fetchCib,
  fetchCrossPollination,
  fetchNearDuplicates,
  fetchNarrativeCrossPollinationHits,
  fetchPosts,
  fetchPropagationGraph,
  fetchSentimentShift,
  fetchThemes,
  getSnapshotGeneratedAt,
  listNarratives,
  loadSnapshot,
} from "./api";
import {
  analysisLayoutHtml,
  analysisSectionFromUrl,
  bindAnalysisSectionNav,
  panelRollupHtml,
  setAnalysisSectionInUrl,
  showAnalysisSection,
  type AnalysisSection,
} from "./analysis-sections";
import { bindBriefPrint, briefPanelHtml, renderBrief } from "./brief";
import { renderContentNotice } from "./content-notice";
import {
  duplicatePanelCaption,
  duplicatePanelTitle,
  postsPanelCalloutHtml,
  renderDataLinksExtra,
  renderRateFooter,
} from "./dashboard-meta";
import {
  crossPollinationPanelHtml,
  renderGlobalCrossPollination,
  renderNarrativeCrossPollination,
} from "./cross-pollination";
import {
  bindFuzzyJaccardHud,
  fuzzyAmplificationPanelHtml,
  renderFuzzyClusters,
  syncJaccardThresholdHud,
  updateFuzzyThresholdBadge,
} from "./fuzzy-amplification";
import {
  applyClusterTagsToPosts,
  loadStoredThreshold,
  recomputeNearDuplicatesReport,
  resolveThresholdBounds,
  storeThreshold,
} from "./near-duplicate-clustering";
import { renderMethodology } from "./methodology";
import {
  bindTabNav,
  renderTabNav,
  showTabPanel,
  setTabInUrl,
  tabFromUrl,
  type AppTab,
} from "./tabs";
import {
  clearInvestigationFilter,
  filterPosts,
  getInvestigationFilter,
  hasActiveFilter,
  onInvestigationChange,
  selectAuthor,
  selectDate,
  selectDuplicateCluster,
  setHoursBack,
  setInvestigationPosts,
} from "./investigation";
import {
  bindPostListAuthorLinks,
  escapeHtml,
  renderPostsList,
  truncate,
} from "./post-display";
import {
  clearThemeCardSelection,
  emergingThemesBadge,
  emergingThemesPanelHtml,
  renderEmergingThemesTimeline,
} from "./emerging-themes";
import {
  focusPropagationAuthor,
  graphPanelHtml,
  renderPropagationGraph,
  setPropagationAuthorHandler,
  updatePropagationGraphBadge,
} from "./propagation-graph";
import {
  buildAuthorPriorityPoints,
  mountPrioritizationScatter,
  priorityScatterPanelHtml,
  renderPriorityTargetList,
} from "./prioritization-scatter";
import { computeOutrageDiagnostics } from "./outrage-diagnostics";
import { mountSentimentChart, sentimentChartPanelHtml } from "./sentiment-chart";
import type {
  AmplificationReport,
  CibReport,
  DuplicateCluster,
  NarrativeSummary,
  NearDuplicatesReport,
  Post,
  ThemesReport,
} from "./types";

const BLUR_SENSITIVE_KEY = "heimdall-blur-sensitive";
const COMPACT_CHARTS_KEY = "heimdall-compact-charts";
const POST_LIST_INITIAL = 20;
const POST_LIST_MAX = 50;

let currentTab: AppTab = tabFromUrl();
let currentAnalysisSection: AnalysisSection = analysisSectionFromUrl();
let blurSensitive = localStorage.getItem(BLUR_SENSITIVE_KEY) === "1";
let compactCharts = localStorage.getItem(COMPACT_CHARTS_KEY) !== "0";
let groupAuthorPosts = true;
let postListLimit = POST_LIST_INITIAL;
let lastNearDup: NearDuplicatesReport | null = null;
let clusterSourcePosts: Post[] = [];
let jaccardThreshold = 0.82;
let briefContext: {
  narrative: NarrativeSummary;
  posts: Post[];
  cib: CibReport;
  amp: AmplificationReport;
  themes: ThemesReport;
  crossPollination: import("./types").CrossPollinationReport | null;
} | null = null;

type ChartMountFns = {
  mountOverview: () => void;
  mountSignals: () => void;
  mountGraphs: () => void;
  mountAnomalies: () => void;
};
let chartMountFns: ChartMountFns | null = null;
const chartsMounted = {
  overview: false,
  signals: false,
  graphs: false,
  anomalies: false,
};

const rootEl = document.getElementById("app");
if (!rootEl) throw new Error("#app missing");
const root: HTMLElement = rootEl;

applyChartDensity();

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

function scrollPageToTop(): void {
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
}

function applyChartDensity(): void {
  document.documentElement.classList.toggle("chart-density-compact", compactCharts);
}

function switchAnalysisSection(section: AnalysisSection, options?: { scroll?: boolean }): void {
  currentAnalysisSection = section;
  setAnalysisSectionInUrl(section);
  showAnalysisSection(section);
  ensureChartsMountedForSection(section);
  if (options?.scroll !== false) {
    document
      .querySelector(`[data-analysis-section-panel="${section}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function ensureChartsMountedForSection(section: AnalysisSection): void {
  if (!chartMountFns) return;
  if (section === "overview" && !chartsMounted.overview) {
    chartsMounted.overview = true;
    chartMountFns.mountOverview();
  }
  if (section === "signals" && !chartsMounted.signals) {
    chartsMounted.signals = true;
    chartMountFns.mountSignals();
  }
  if (section === "graphs" && !chartsMounted.graphs) {
    chartsMounted.graphs = true;
    chartMountFns.mountGraphs();
  }
  if (section === "anomalies" && !chartsMounted.anomalies) {
    chartsMounted.anomalies = true;
    chartMountFns.mountAnomalies();
  }
}

function syncRailInvestigation(): void {
  const rail = document.getElementById("analysis-rail-investigation");
  const bar = document.getElementById("investigation-filter-bar");
  if (!rail || !bar) return;
  if (bar.hidden) {
    rail.hidden = true;
    rail.innerHTML = "";
    return;
  }
  rail.hidden = false;
  rail.innerHTML = `<span class="investigation-label">Active filter</span>${bar.innerHTML.replace(/<span class="investigation-label">Investigating:<\/span>\s*/i, "")}`;
}

function mean(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function outrageHistogram(posts: Post[]): Map<string, number> {
  const bins = new Map<string, number>([
    ["0-0.2", 0],
    ["0.2-0.4", 0],
    ["0.4-0.6", 0],
    ["0.6-0.8", 0],
    ["0.8-1.0", 0],
    ["(none)", 0],
  ]);
  for (const p of posts) {
    const o = p.outrage_index;
    if (o == null) {
      bins.set("(none)", (bins.get("(none)") ?? 0) + 1);
      continue;
    }
    if (o < 0.2) bins.set("0-0.2", (bins.get("0-0.2") ?? 0) + 1);
    else if (o < 0.4) bins.set("0.2-0.4", (bins.get("0.2-0.4") ?? 0) + 1);
    else if (o < 0.6) bins.set("0.4-0.6", (bins.get("0.4-0.6") ?? 0) + 1);
    else if (o < 0.8) bins.set("0.6-0.8", (bins.get("0.6-0.8") ?? 0) + 1);
    else bins.set("0.8-1.0", (bins.get("0.8-1.0") ?? 0) + 1);
  }
  return bins;
}

function renderHistogram(posts: Post[]): string {
  const bins = outrageHistogram(posts);
  const max = Math.max(1, ...bins.values());
  const rows = [...bins.entries()]
    .map(([label, count]) => {
      const pct = (count / max) * 100;
      return `<div class="bar-row">
        <span class="bar-label">${escapeHtml(label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <span>${count}</span>
      </div>`;
    })
    .join("");
  return `<div class="chart">${rows}</div>`;
}

function applyJaccardThreshold(threshold: number): void {
  jaccardThreshold = threshold;
  storeThreshold(threshold);
  if (!clusterSourcePosts.length) return;
  lastNearDup = recomputeNearDuplicatesReport(
    clusterSourcePosts,
    threshold,
    lastNearDup
  );
  setInvestigationPosts(applyClusterTagsToPosts(clusterSourcePosts, lastNearDup));
  const fuzzyHost = document.getElementById("fuzzy-clusters-host");
  if (fuzzyHost) renderFuzzyClusters(fuzzyHost, lastNearDup, { pulse: true });
  updateFuzzyThresholdBadge(threshold, lastNearDup.cross_author_fuzzy_count ?? 0);
  syncJaccardThresholdHud(threshold, resolveThresholdBounds(lastNearDup));
  updatePostsPanel();
}

function updatePostsPanel(): void {
  const host = document.getElementById("post-list-host");
  const bar = document.getElementById("investigation-filter-bar");
  const countEl = document.getElementById("post-list-count");
  if (!host) return;

  const filtered = filterPosts();
  const active = getInvestigationFilter();
  host.innerHTML = renderPostsList(filtered, {
    limit: postListLimit,
    activeAuthorId: active.authorId,
    blurSensitive,
    nearDup: lastNearDup,
    groupAuthors: groupAuthorPosts,
  });
  bindPostListAuthorLinks(host);
  const loadMore = document.getElementById("load-more-posts");
  const canLoadMore =
    filtered.length > postListLimit && postListLimit < POST_LIST_MAX;
  if (loadMore) {
    if (canLoadMore) {
      loadMore.removeAttribute("hidden");
      loadMore.textContent = `Show more posts (${Math.min(POST_LIST_MAX, filtered.length) - postListLimit} more)`;
    } else {
      loadMore.setAttribute("hidden", "");
    }
  }
  if (countEl) {
    const shown = Math.min(postListLimit, filtered.length);
    countEl.textContent = hasActiveFilter()
      ? `${shown} of ${filtered.length} matching`
      : `Top ${shown} of ${filtered.length} by outrage`;
  }
  syncRailInvestigation();
  if (bar) {
    const f = getInvestigationFilter();
    if (hasActiveFilter() && f.label) {
      bar.hidden = false;
      bar.innerHTML = `<span class="investigation-label">Investigating:</span> <strong>${escapeHtml(f.label)}</strong>`;
    } else {
      bar.hidden = true;
      bar.innerHTML = "";
    }
  }
}

function applyInvestigation(authorId: string | null): void {
  focusPropagationAuthor(authorId);
  updatePostsPanel();
  if (hasActiveFilter()) {
    switchAnalysisSection("posts");
  }
}

function bindInvestigationChrome(): void {
  const clearBtn = document.getElementById("clear-investigation");
  clearBtn?.addEventListener("click", () => {
    clearThemeCardSelection();
    clearInvestigationFilter();
  });
  onInvestigationChange((f) => {
    applyInvestigation(f.authorId);
    if (!f.postIds?.length) clearThemeCardSelection();
    if (hasActiveFilter()) clearBtn?.removeAttribute("hidden");
    else {
      clearBtn?.setAttribute("hidden", "");
      clearThemeCardSelection();
    }
  });
}

function renderClustersBlock(clusters: DuplicateCluster[], max = 8): string {
  if (clusters.length === 0) {
    return "<p class='loading'>No exact duplicate-text clusters (need ≥2 posts with identical normalized text).</p>";
  }
  return clusters
    .slice(0, max)
    .map((c) => {
      const burst = c.burst_synchronized
        ? `<span class="burst-tag">${c.burst_author_count ?? c.author_count} authors in 90s burst</span>`
        : "";
      const timing =
        c.min_inter_arrival_seconds != null
          ? ` · min gap ${c.min_inter_arrival_seconds}s · span ${c.cluster_span_seconds ?? "?"}s`
          : "";
      const ids = c.post_ids.join(",");
      return `<button type="button" class="cluster cluster-btn${c.burst_synchronized ? " cluster-burst" : ""}" data-post-ids="${ids}" data-burst="${c.burst_synchronized ? "1" : "0"}">
        <strong>${c.count} posts</strong> · ${c.author_count} authors${burst}
        <p class="post-text">${escapeHtml(truncate(c.sample_text, 200))}</p>
        <p class="post-meta">authors: ${escapeHtml(c.author_ids.slice(0, 5).join(", "))}${c.author_ids.length > 5 ? "…" : ""}${timing}</p>
      </button>`;
    })
    .join("");
}

function renderDuplicatesInner(clusters: DuplicateCluster[]): string {
  return `
    <h2>${duplicatePanelTitle()}</h2>
    ${duplicatePanelCaption()}
    <div id="dup-clusters-host">${renderClustersBlock(clusters)}</div>
  `;
}

function renderDuplicatesPanel(
  clusters: DuplicateCluster[],
  mode: "preview" | "full"
): string {
  if (mode === "preview") {
    const top = clusters.slice(0, 3);
    const rest = clusters.slice(3, 8);
    return `
      <section class="panel panel-duplicates">
        <h2>${duplicatePanelTitle()}</h2>
        <p class="chart-caption dup-legend">
          Top clusters here — open <strong>Anomalies</strong> for the full list and fuzzy/cross-narrative panels.
        </p>
        <div id="dup-clusters-host-overview">${renderClustersBlock(top, 3)}</div>
        ${
          rest.length
            ? panelRollupHtml(
                `${rest.length} more exact-duplicate cluster${rest.length === 1 ? "" : "s"}`,
                renderClustersBlock(rest, 8)
              )
            : ""
        }
      </section>
    `;
  }
  return `<section class="panel panel-duplicates">${renderDuplicatesInner(clusters)}</section>`;
}

function metricsGridHtml(
  posts: Post[],
  authors: Set<string>,
  avg: number | null,
  cib: CibReport
): string {
  return `
    <div class="metrics-grid">
      <div class="metric-card"><span class="metric-label">Posts</span><div class="metric-value">${posts.length}</div></div>
      <div class="metric-card"><span class="metric-label">Authors</span><div class="metric-value">${authors.size}</div></div>
      <div class="metric-card"><span class="metric-label">Mean outrage</span><div class="metric-value">${avg != null ? avg.toFixed(3) : "n/a"}</div></div>
      <div class="metric-card metric-card-wide">
        <span class="metric-label">CIB suspicion</span>
        <div class="metric-value">${cib.suspicion_score.toFixed(2)}</div>
        <div class="metric-sub">organic ${cib.organic_score.toFixed(2)} · ${cib.edge_count} edges</div>
      </div>
    </div>
  `;
}

function cibSnapshotHtml(cib: CibReport): string {
  const signals = cib.signals.slice(0, 3);
  return `
    <section class="panel panel-cib-snapshot">
      <h2>CIB at a glance</h2>
      ${
        signals.length
          ? `<ul class="signal-list signal-list-compact">${signals.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
          : "<p class='empty'>No elevated CIB signals.</p>"
      }
      ${
        cib.iu_astroturf
          ? `<p class="metric-sub">IU astroturf: ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors</p>`
          : ""
      }
    </section>
  `;
}

function analysisSectionHiddenAttr(section: AnalysisSection): string {
  return section === currentAnalysisSection ? "" : " hidden";
}

function bindClusterButtons(): void {
  document.querySelectorAll<HTMLButtonElement>(".cluster-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ids = (btn.dataset.postIds ?? "")
        .split(",")
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isFinite(n));
      const burst = btn.dataset.burst === "1";
      const sample = btn.querySelector(".post-text")?.textContent ?? "cluster";
      selectDuplicateCluster(sample.slice(0, 40), ids, burst);
      switchAnalysisSection("posts");
    });
  });
}

function bindPostToolbar(): void {
  document.getElementById("time-range-select")?.addEventListener("change", (e) => {
    const v = (e.target as HTMLSelectElement).value;
    setHoursBack(v ? parseInt(v, 10) : null);
  });
  document.getElementById("blur-sensitive-toggle")?.addEventListener("change", (e) => {
    blurSensitive = (e.target as HTMLInputElement).checked;
    localStorage.setItem(BLUR_SENSITIVE_KEY, blurSensitive ? "1" : "0");
    updatePostsPanel();
  });
  document.getElementById("group-authors-toggle")?.addEventListener("change", (e) => {
    groupAuthorPosts = (e.target as HTMLInputElement).checked;
    updatePostsPanel();
  });
  document.getElementById("compact-charts-toggle")?.addEventListener("change", (e) => {
    compactCharts = (e.target as HTMLInputElement).checked;
    localStorage.setItem(COMPACT_CHARTS_KEY, compactCharts ? "1" : "0");
    applyChartDensity();
  });
  document.getElementById("load-more-posts")?.addEventListener("click", () => {
    postListLimit = POST_LIST_MAX;
    updatePostsPanel();
  });
}

function refreshBriefPanel(): void {
  const host = document.getElementById("brief-content");
  if (!host || !briefContext) return;
  renderBrief(
    host,
    briefContext.narrative,
    briefContext.posts,
    briefContext.cib,
    briefContext.amp,
    briefContext.themes,
    lastNearDup,
    briefContext.crossPollination ?? null
  );
}

function shell(narratives: NarrativeSummary[], selectedId: number, generatedAt: string | null): string {
  const options = narratives
    .map(
      (n) =>
        `<option value="${n.id}" ${n.id === selectedId ? "selected" : ""}>${escapeHtml(n.name)} (${n.post_count} posts)</option>`
    )
    .join("");
  const stamp = generatedAt ? ` · ${escapeHtml(generatedAt.slice(0, 19))} UTC` : "";
  return `
    <div class="app">
      <header class="site-header">
        <div class="header-top">
          <h1><span class="brand">Heimdall</span> Narrative Analysis</h1>
          <p class="data-badge">Repo snapshot${stamp}</p>
        </div>
        ${renderContentNotice()}
        <details class="header-meta-collapse">
          <summary class="header-meta-summary">Data sources &amp; ingest</summary>
          <p class="data-links">Source data: ${renderDataLinksExtra()}</p>
          ${renderRateFooter()}
        </details>
      </header>
      ${renderTabNav(currentTab)}
      <div id="panel-analysis"${currentTab !== "analysis" ? " hidden" : ""}>
        <div class="toolbar">
          <div class="toolbar-inner">
            <label for="narrative-select">Narrative</label>
            <select id="narrative-select" class="narrative-select">${options}</select>
            <label for="time-range-select" class="toolbar-label">Window</label>
            <select id="time-range-select" class="toolbar-select" aria-label="Time window">
              <option value="">All time</option>
              <option value="24">Last 24h</option>
              <option value="72">Last 72h</option>
              <option value="168">Last 7d</option>
            </select>
            <label class="toolbar-check"><input type="checkbox" id="group-authors-toggle" checked /> Group busy authors</label>
            <label class="toolbar-check"><input type="checkbox" id="blur-sensitive-toggle" ${blurSensitive ? "checked" : ""} /> Blur sensitive text</label>
            <label class="toolbar-check"><input type="checkbox" id="compact-charts-toggle" ${compactCharts ? "checked" : ""} /> Compact charts</label>
            <button type="button" id="refresh-btn" class="btn btn-secondary">Reload snapshot</button>
          </div>
        </div>
        <main id="content" class="dashboard"><p class="loading">Loading…</p></main>
      </div>
      <div id="panel-brief" class="panel-brief"${currentTab !== "brief" ? " hidden" : ""}>
        <main class="dashboard">${briefPanelHtml()}</main>
      </div>
      <div id="panel-methodology" class="panel-methodology"${currentTab !== "methodology" ? " hidden" : ""}>
        <main class="dashboard prose-wrap">${renderMethodology()}</main>
      </div>
    </div>
  `;
}

function switchTab(tab: AppTab): void {
  currentTab = tab;
  setTabInUrl(tab);
  showTabPanel(tab);
  if (tab === "brief") refreshBriefPanel();
}

function renderMissingSnapshot(message: string): void {
  root.innerHTML = `
    <header class="site-header">
      <h1><span class="brand">Heimdall</span> Narrative Analysis</h1>
      ${renderContentNotice()}
    </header>
    <main>
      <div class="error">
        <strong>No snapshot data</strong>
        <p>${escapeHtml(message)}</p>
        <p class="sub">Publish ingest to the repo with <code>python scripts/publish_dashboard_data.py</code>, then redeploy Pages.</p>
        <p class="data-links">
          <a href="${DATA_LINKS.publishDocs}" target="_blank" rel="noopener">data/dashboard/README.md</a>
        </p>
      </div>
    </main>
  `;
}

async function loadDashboard(narrativeId: number): Promise<void> {
  const content = document.getElementById("content");
  if (!content) return;
  content.innerHTML = "<p class='loading'>Loading…</p>";

  try {
    const narratives = await listNarratives();
    const narrativeMeta = narratives.find((n) => n.id === narrativeId);
    const [posts, cib, sentiment, amp, graph, themes, nearDup, benchmark, crossPollination, pollinationHits] =
      await Promise.all([
        fetchPosts(narrativeId),
        fetchCib(narrativeId),
        fetchSentimentShift(narrativeId),
        fetchAmplification(narrativeId),
        fetchPropagationGraph(narrativeId),
        fetchThemes(narrativeId),
        fetchNearDuplicates(narrativeId),
        fetchBenchmark(narrativeId),
        fetchCrossPollination(),
        fetchNarrativeCrossPollinationHits(narrativeId),
      ]);
    clusterSourcePosts = posts;
    const bounds = resolveThresholdBounds(nearDup);
    jaccardThreshold = loadStoredThreshold(
      bounds.defaultThreshold,
      bounds.min,
      bounds.max
    );
    lastNearDup = recomputeNearDuplicatesReport(posts, jaccardThreshold, nearDup);
    setInvestigationPosts(applyClusterTagsToPosts(posts, lastNearDup));
    if (narrativeMeta) {
      briefContext = {
        narrative: narrativeMeta,
        posts,
        cib,
        amp,
        themes,
        crossPollination,
      };
      refreshBriefPanel();
    }

    const scored = posts.filter((p) => p.outrage_index != null);
    const outrageVals = scored.map((p) => p.outrage_index as number);
    const authors = new Set(posts.map((p) => p.author_id));
    const avg = mean(outrageVals);
    const outrageDiag = computeOutrageDiagnostics(posts, sentiment.buckets);
    const priorityPoints = buildAuthorPriorityPoints(graph, cib, posts);
    const criticalCount = priorityPoints.filter((p) => p.critical).length;
    const fuzzyCount = lastNearDup?.cross_author_fuzzy_count ?? 0;
    const crossActorCount = crossPollination?.actor_count ?? 0;
    const dupCount = amp.clusters.length;

    postListLimit = POST_LIST_INITIAL;
    chartsMounted.overview = false;
    chartsMounted.signals = false;
    chartsMounted.graphs = false;
    chartsMounted.anomalies = false;

    const sectionPanels = `
      <section class="analysis-section" data-analysis-section-panel="overview"${analysisSectionHiddenAttr("overview")}>
        <div class="metrics-histogram-row">
          ${metricsGridHtml(posts, authors, avg, cib)}
          <section class="panel panel-histogram-compact">
            <h2>Outrage distribution</h2>
            ${renderHistogram(posts)}
          </section>
        </div>
        ${sentimentChartPanelHtml(escapeHtml(sentiment.trend), outrageDiag)}
        ${cibSnapshotHtml(cib)}
        ${renderDuplicatesPanel(amp.clusters, "preview")}
        ${panelRollupHtml(
          `Emerging themes ${emergingThemesBadge(themes)}`,
          `<div class="panel panel-chart-wide themes-panel">${emergingThemesPanelHtml(themes, true)}</div>`
        )}
      </section>

      <section class="analysis-section" data-analysis-section-panel="signals"${analysisSectionHiddenAttr("signals")}>
        ${priorityScatterPanelHtml(criticalCount, graph.edges.length, outrageDiag)}
        <section class="panel">
          <h2>CIB signals</h2>
          <div class="signal-body">
            ${cib.signals.length ? `<ul class="signal-list">${cib.signals.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : "<p class='empty'>No elevated CIB signals.</p>"}
            ${
              cib.iu_astroturf
                ? `<p class="metric-sub">IU astroturf: ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors</p>`
                : ""
            }
          </div>
        </section>
      </section>

      <section class="analysis-section" data-analysis-section-panel="graphs"${analysisSectionHiddenAttr("graphs")}>
        ${graphPanelHtml()}
      </section>

      <section class="analysis-section" data-analysis-section-panel="anomalies"${analysisSectionHiddenAttr("anomalies")}>
        ${panelRollupHtml(
          `Exact duplicate text (${dupCount} cluster${dupCount === 1 ? "" : "s"})`,
          `<div class="panel panel-duplicates">${renderDuplicatesInner(amp.clusters)}</div>`
        )}
        ${panelRollupHtml(
          `Cross-author fuzzy amplification (${fuzzyCount} cluster${fuzzyCount === 1 ? "" : "s"})`,
          fuzzyAmplificationPanelHtml(nearDup, jaccardThreshold, bounds, true)
        )}
        ${panelRollupHtml(
          `Narrative cross-pollination (${crossActorCount} cross-narrative actor${crossActorCount === 1 ? "" : "s"})`,
          crossPollinationPanelHtml(crossPollination, true)
        )}
      </section>

      <section class="analysis-section posts-section" data-analysis-section-panel="posts"${analysisSectionHiddenAttr("posts")}>
        <section class="panel posts-panel" id="posts-panel">
          <div class="posts-panel-header">
            <h2>Posts <span class="post-list-count" id="post-list-count"></span></h2>
            <div id="investigation-filter-bar" class="investigation-bar" hidden></div>
            <button type="button" id="clear-investigation" class="btn btn-secondary btn-small" hidden>
              Clear filter
            </button>
          </div>
          ${postsPanelCalloutHtml()}
          <div id="post-list-host"></div>
          <button type="button" id="load-more-posts" class="btn btn-secondary btn-small load-more-posts" hidden>
            Show more posts
          </button>
        </section>
        ${
          benchmark
            ? `<p class="panel-callout benchmark-callout">Benchmark labels: ${benchmark.labeled_posts}/${benchmark.total_posts} posts (${escapeHtml(benchmark.labels.join(", "))}).</p>`
            : ""
        }
      </section>
    `;

    content.innerHTML = analysisLayoutHtml(sectionPanels, currentAnalysisSection);

    clearInvestigationFilter();

    const pickAuthor = (authorId: string, label: string) => {
      selectAuthor(authorId, label);
    };

    chartMountFns = {
      mountOverview: () => {
        const sentimentCanvas = document.getElementById(
          "sentiment-timeline-chart"
        ) as HTMLCanvasElement | null;
        if (sentimentCanvas) {
          mountSentimentChart(
            sentimentCanvas,
            sentiment.buckets,
            (date) => selectDate(date),
            outrageDiag
          );
        }
        const themesHost = document.getElementById("themes-timeline-host");
        if (themesHost && themesHost.dataset.mounted !== "1") {
          themesHost.dataset.mounted = "1";
          renderEmergingThemesTimeline(themesHost, themes);
        }
      },
      mountSignals: () => {
        const scatterCanvas = document.getElementById(
          "priority-scatter-chart"
        ) as HTMLCanvasElement | null;
        const targetList = document.getElementById("priority-target-list");
        if (scatterCanvas) {
          mountPrioritizationScatter(
            scatterCanvas,
            priorityPoints,
            (point) => pickAuthor(point.author_id, point.label),
            graph.edges.length,
            outrageDiag
          );
        }
        if (targetList) {
          renderPriorityTargetList(
            targetList,
            priorityPoints,
            (point) => pickAuthor(point.author_id, point.label),
            graph.edges.length,
            outrageDiag
          );
        }
      },
      mountGraphs: () => {
        setPropagationAuthorHandler((authorId) => {
          const author = graph.authors.find((a) => a.author_id === authorId);
          const label = author?.handle ? `@${author.handle}` : authorId.slice(0, 12);
          pickAuthor(authorId, label);
        });
        const graphEl = document.getElementById("propagation-graph");
        if (graphEl) {
          const meta = renderPropagationGraph(graphEl, graph, cib);
          updatePropagationGraphBadge(meta);
        }
      },
      mountAnomalies: () => {},
    };

    const fuzzyHost = document.getElementById("fuzzy-clusters-host");
    if (fuzzyHost) renderFuzzyClusters(fuzzyHost, lastNearDup);
    updateFuzzyThresholdBadge(jaccardThreshold, fuzzyCount);
    const crossGlobalHost = document.getElementById("cross-pollination-global-host");
    if (crossGlobalHost) renderGlobalCrossPollination(crossGlobalHost, crossPollination);
    const crossNarrativeHost = document.getElementById("cross-pollination-narrative-host");
    if (crossNarrativeHost && narrativeMeta) {
      renderNarrativeCrossPollination(
        crossNarrativeHost,
        pollinationHits,
        narrativeMeta.name,
        narrativeId
      );
    }

    bindAnalysisSectionNav((section) => switchAnalysisSection(section));
    bindInvestigationChrome();
    bindClusterButtons();
    bindPostToolbar();
    bindFuzzyJaccardHud(applyJaccardThreshold);
    bindBriefPrint();
    bindPostListAuthorLinks(document.getElementById("post-list-host") ?? document);
    updatePostsPanel();
    ensureChartsMountedForSection(currentAnalysisSection);
    scrollPageToTop();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    content.innerHTML = `<div class="error"><strong>Failed to load narrative ${narrativeId}</strong><p>${escapeHtml(msg)}</p></div>`;
    scrollPageToTop();
  }
}

function narrativeIdFromUrl(): number | null {
  const p = new URLSearchParams(window.location.search);
  const n = p.get("narrative");
  if (!n) return null;
  const id = parseInt(n, 10);
  return Number.isFinite(id) ? id : null;
}

function setUrlNarrative(id: number): void {
  const url = new URL(window.location.href);
  url.searchParams.set("narrative", String(id));
  window.history.replaceState({}, "", url);
}

async function reloadSnapshotFromNetwork(narrativeId: number): Promise<void> {
  const refresh = document.getElementById("refresh-btn") as HTMLButtonElement | null;
  const stamp = document.querySelector(".data-badge");
  if (refresh) {
    refresh.disabled = true;
    refresh.textContent = "Reloading…";
  }
  clearSnapshotCache();
  try {
    await loadSnapshot({ bustCache: true });
    const narratives = await listNarratives();
    const select = document.getElementById("narrative-select") as HTMLSelectElement | null;
    if (select) {
      select.innerHTML = narratives
        .map(
          (n) =>
            `<option value="${n.id}" ${n.id === narrativeId ? "selected" : ""}>${escapeHtml(n.name)} (${n.post_count} posts)</option>`
        )
        .join("");
    }
    if (stamp) {
      const at = getSnapshotGeneratedAt();
      stamp.textContent = at
        ? `Repo snapshot · ${escapeHtml(at.slice(0, 19))} UTC (reloaded)`
        : "Repo snapshot (reloaded)";
    }
    await loadDashboard(narrativeId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const content = document.getElementById("content");
    if (content) {
      content.innerHTML = `<div class="error"><strong>Reload failed</strong><p>${escapeHtml(msg)}</p><p class="sub">GitHub Pages may still be deploying after ingest. Wait 1–2 minutes and try again.</p></div>`;
    }
  } finally {
    if (refresh) {
      refresh.disabled = false;
      refresh.textContent = "Reload snapshot";
    }
  }
}

function bindDashboardControls(narratives: NarrativeSummary[], initialId: number): void {
  let selected = initialId;
  const select = document.getElementById("narrative-select") as HTMLSelectElement;
  const refresh = document.getElementById("refresh-btn");

  const run = () => {
    selected = parseInt(select.value, 10);
    setUrlNarrative(selected);
    void loadDashboard(selected);
  };

  select.addEventListener("change", run);
  refresh?.addEventListener("click", () => {
    void reloadSnapshotFromNetwork(selected);
  });
  run();
}

async function bootstrap(): Promise<void> {
  try {
    await loadSnapshot();
    const narratives = await listNarratives();
    if (narratives.length === 0) {
      renderMissingSnapshot("Snapshot has no narratives.");
      return;
    }

    const selected =
      narrativeIdFromUrl() ??
      narratives.find((n) => n.name === "midterms_2026")?.id ??
      narratives[0].id;

    root.innerHTML = shell(narratives, selected, getSnapshotGeneratedAt());
    scrollPageToTop();
    bindTabNav(switchTab);
    bindDashboardControls(narratives, selected);
    bindPostToolbar();
    bindBriefPrint();
    showTabPanel(currentTab);
    if (currentTab === "brief") refreshBriefPanel();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    renderMissingSnapshot(msg);
  }
}

window.addEventListener("heimdall:goto-posts", () => {
  if (currentTab === "analysis") switchAnalysisSection("posts");
});

void bootstrap();

import {
  clearSnapshotCache,
  DATA_LINKS,
  fetchAmplification,
  fetchBenchmark,
  fetchCib,
  fetchNearDuplicates,
  fetchPosts,
  fetchPropagationGraph,
  fetchSentimentShift,
  fetchThemes,
  getSnapshotGeneratedAt,
  listNarratives,
  loadSnapshot,
} from "./api";
import { bindBriefPrint, briefPanelHtml, renderBrief } from "./brief";
import { renderContentNotice } from "./content-notice";
import {
  duplicatePanelCaption,
  duplicatePanelTitle,
  postsPanelCalloutHtml,
  renderDataLinksExtra,
  renderRateFooter,
} from "./dashboard-meta";
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
  emergingThemesPanelHtml,
  renderEmergingThemesTimeline,
} from "./emerging-themes";
import {
  focusPropagationAuthor,
  graphPanelHtml,
  renderPropagationGraph,
  setPropagationAuthorHandler,
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

let currentTab: AppTab = tabFromUrl();
let blurSensitive = localStorage.getItem(BLUR_SENSITIVE_KEY) === "1";
let groupAuthorPosts = true;
let lastNearDup: NearDuplicatesReport | null = null;
let briefContext: {
  narrative: NarrativeSummary;
  posts: Post[];
  cib: CibReport;
  amp: AmplificationReport;
  themes: ThemesReport;
} | null = null;

const rootEl = document.getElementById("app");
if (!rootEl) throw new Error("#app missing");
const root: HTMLElement = rootEl;

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

function scrollPageToTop(): void {
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
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

function updatePostsPanel(): void {
  const host = document.getElementById("post-list-host");
  const bar = document.getElementById("investigation-filter-bar");
  const countEl = document.getElementById("post-list-count");
  if (!host) return;

  const filtered = filterPosts();
  const active = getInvestigationFilter();
  host.innerHTML = renderPostsList(filtered, {
    limit: 50,
    activeAuthorId: active.authorId,
    blurSensitive,
    nearDup: lastNearDup,
    groupAuthors: groupAuthorPosts,
  });
  bindPostListAuthorLinks(host);
  if (countEl) {
    countEl.textContent = hasActiveFilter()
      ? `${filtered.length} matching posts`
      : `Top ${Math.min(50, filtered.length)} by outrage`;
  }
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
    document.getElementById("posts-panel")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
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

function renderClusters(clusters: DuplicateCluster[]): string {
  if (clusters.length === 0) {
    return "<p class='loading'>No exact duplicate-text clusters (need ≥2 posts with identical normalized text).</p>";
  }
  return clusters
    .slice(0, 8)
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
      document.getElementById("posts-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
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
    briefContext.themes
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
        <p class="data-links">Source data: ${renderDataLinksExtra()}</p>
        ${renderRateFooter()}
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
    const narrativeMeta = (await listNarratives()).find((n) => n.id === narrativeId);
    const [posts, cib, sentiment, amp, graph, themes, nearDup, benchmark] =
      await Promise.all([
        fetchPosts(narrativeId),
        fetchCib(narrativeId),
        fetchSentimentShift(narrativeId),
        fetchAmplification(narrativeId),
        fetchPropagationGraph(narrativeId),
        fetchThemes(narrativeId),
        fetchNearDuplicates(narrativeId),
        fetchBenchmark(narrativeId),
      ]);
    lastNearDup = nearDup;
    if (narrativeMeta) {
      briefContext = { narrative: narrativeMeta, posts, cib, amp, themes };
      refreshBriefPanel();
    }

    const scored = posts.filter((p) => p.outrage_index != null);
    const outrageVals = scored.map((p) => p.outrage_index as number);
    const authors = new Set(posts.map((p) => p.author_id));
    const avg = mean(outrageVals);
    const outrageDiag = computeOutrageDiagnostics(posts, sentiment.buckets);
    const priorityPoints = buildAuthorPriorityPoints(graph, cib, posts);
    const criticalCount = priorityPoints.filter((p) => p.critical).length;

    content.innerHTML = `
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

      <div class="charts-grid">
        <section class="panel">
          <h2>Outrage distribution</h2>
          ${renderHistogram(posts)}
        </section>
      </div>

      ${sentimentChartPanelHtml(escapeHtml(sentiment.trend), outrageDiag)}

      ${priorityScatterPanelHtml(criticalCount, graph.edges.length, outrageDiag)}

      ${graphPanelHtml(null)}

      ${emergingThemesPanelHtml(themes)}

      <div class="split-grid">
        <section class="panel panel-duplicates">
          <h2>${duplicatePanelTitle()}</h2>
          ${duplicatePanelCaption()}
          <div id="dup-clusters-host">${renderClusters(amp.clusters)}</div>
        </section>
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
      </div>

      ${
        benchmark
          ? `<p class="panel-callout benchmark-callout">Benchmark labels: ${benchmark.labeled_posts}/${benchmark.total_posts} posts (${escapeHtml(benchmark.labels.join(", "))}).</p>`
          : ""
      }

      <section class="panel posts-panel" id="posts-panel">
        <div class="posts-panel-header">
          <h2>Posts <span class="post-list-count" id="post-list-count"></span></h2>
          <div id="investigation-filter-bar" class="investigation-bar" hidden></div>
          <button type="button" id="clear-investigation" class="btn btn-secondary btn-small" hidden>
            Clear filter
          </button>
        </div>
        ${postsPanelCalloutHtml()}
        <div id="post-list-host">${renderPostsList(posts, {
          limit: 50,
          blurSensitive,
          nearDup,
          groupAuthors: groupAuthorPosts,
        })}</div>
      </section>
    `;

    setInvestigationPosts(posts);
    clearInvestigationFilter();

    const pickAuthor = (authorId: string, label: string) => {
      selectAuthor(authorId, label);
    };

    const sentimentCanvas = document.getElementById(
      "sentiment-timeline-chart"
    ) as HTMLCanvasElement | null;
    if (sentimentCanvas) {
      mountSentimentChart(
        sentimentCanvas,
        sentiment.buckets,
        (date) => {
          selectDate(date);
        },
        outrageDiag
      );
    }

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

    setPropagationAuthorHandler((authorId) => {
      const author = graph.authors.find((a) => a.author_id === authorId);
      const label = author?.handle ? `@${author.handle}` : authorId.slice(0, 12);
      pickAuthor(authorId, label);
    });

    const graphEl = document.getElementById("propagation-graph");
    if (graphEl) {
      const meta = renderPropagationGraph(graphEl, graph, cib);
      const badgeHost = graphEl.parentElement?.querySelector("h2");
      if (badgeHost) {
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
    }

    const themesHost = document.getElementById("themes-timeline-host");
    if (themesHost) renderEmergingThemesTimeline(themesHost, themes);

    bindInvestigationChrome();
    bindClusterButtons();
    bindPostToolbar();
    bindBriefPrint();
    bindPostListAuthorLinks(document.getElementById("post-list-host") ?? document);
    updatePostsPanel();
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

void bootstrap();

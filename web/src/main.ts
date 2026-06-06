import {
  clearSnapshotCache,
  DATA_LINKS,
  fetchAmplification,
  fetchBenchmark,
  fetchBrief,
  fetchCib,
  fetchCrossPollination,
  fetchNearDuplicates,
  fetchNarrativeCrossPollinationHits,
  fetchPosts,
  fetchPropagationGraph,
  fetchProvenance,
  fetchSentimentShift,
  fetchThemes,
  getMetricsHistory,
  getPrimaryNarrativeName,
  getSnapshotGeneratedAt,
  listNarratives,
  loadSnapshot,
} from "./api";
import { metricsTrendPanelHtml, mountMetricsTrendChart } from "./app/metrics-trend";
import { buildMetricsGrid, mean, renderHistogram } from "./app/outrage-metrics";
import { renderMissingSnapshot, shell } from "./app/shell";
import {
  appState,
  BLUR_SENSITIVE_KEY,
  COMPACT_CHARTS_KEY,
  POST_LIST_INITIAL,
  POST_LIST_MAX,
  root,
} from "./app/state";
import { narrativeIdFromUrl, setUrlNarrative } from "./app/url-state";
import {
  bindDeskModeNav,
  deskLayoutHtml,
  panelRollupHtml,
  setDeskModeInUrl,
  showDeskMode,
  type DeskMode,
  type ModeBadges,
} from "./desk-modes";
import { bindDeskKeyboard, bindMethodologyDrawer } from "./desk-keyboard";
import {
  bindInspectorViewAuthor,
  bindInspectorViewCluster,
  renderAuthorInspector,
  renderDuplicateClusterInspector,
  resetInspectorEmpty,
  setInspectorContext,
} from "./desk-inspector";
import { buildAlertRows, renderAlertInboxHtml } from "./alert-inbox";
import { findParentThemeLabel, setCoordinationContext } from "./cluster-coordination";
import { bindBriefPrint, renderBrief, resetBriefClipboardBinding } from "./brief";
import {
  duplicatePanelCaption,
  duplicatePanelTitle,
  postsPanelCalloutHtml,
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
import { renderProvenancePanelHtml } from "./provenance-panel";
import {
  bindTabNav,
  showTabPanel,
  setTabInUrl,
  type AppTab,
} from "./tabs";
import {
  clearInvestigationFilter,
  countMatchingPosts,
  filterPosts,
  getInvestigationFilter,
  hasActiveFilter,
  onInvestigationChange,
  selectAuthor,
  selectDate,
  selectDuplicateCluster,
  selectEscalationTier,
  selectThemeCluster,
  setHoursBack,
  setInvestigationPosts,
} from "./investigation";
import { bindOnboardingHint } from "./onboarding-hint";
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
  bindGraphFullscreen,
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
import { buildSentimentAlerts } from "./sentiment-alerts";
import { mountSentimentChart, mountSentimentTierChart, sentimentChartPanelHtml } from "./sentiment-chart";
import {
  bindGlobalInvestigationClear,
  scrollGlobalInvestigationIntoView,
  stateEmptyHtml,
  stateErrorHtml,
  stateLoadingHtml,
  updateGlobalInvestigationBar,
} from "./ui";
import type { CibReport, DuplicateCluster, NarrativeSummary } from "./types";

applyChartDensity();

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

function scrollPageToTop(): void {
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
}

function applyChartDensity(): void {
  document.documentElement.classList.toggle("chart-density-compact", appState.compactCharts);
}

function switchDeskMode(mode: DeskMode, options?: { scroll?: boolean }): void {
  appState.currentDeskMode = mode;
  setDeskModeInUrl(mode);
  showDeskMode(mode);
  ensureChartsMountedForMode(mode);
  if (options?.scroll !== false) {
    document
      .querySelector(`[data-desk-mode-panel="${mode}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function ensureChartsMountedForMode(mode: DeskMode): void {
  if (!appState.chartMountFns) return;
  if (mode === "pulse" && !appState.chartsMounted.pulse) {
    appState.chartsMounted.pulse = true;
    appState.chartMountFns.mountPulse();
  }
  if (mode === "frames" && !appState.chartsMounted.frames) {
    appState.chartsMounted.frames = true;
    appState.chartMountFns.mountFrames();
  }
  if (mode === "network" && !appState.chartsMounted.network) {
    appState.chartsMounted.network = true;
    appState.chartMountFns.mountNetwork();
  }
}

function computeModeBadges(): ModeBadges {
  const badges: ModeBadges = {};
  if (appState.lastCriticalCount > 0) badges.pulse = appState.lastCriticalCount;
  if (appState.lastAnomalyCount > 0) badges.network = appState.lastAnomalyCount;
  if (hasActiveFilter()) {
    badges.evidence = countMatchingPosts();
  } else if (appState.totalNarrativePosts > 0) {
    badges.evidence = appState.totalNarrativePosts;
  }
  return badges;
}

function refreshDeskStrip(): void {
  updateGlobalInvestigationBar(computeModeBadges);
}

function applyJaccardThreshold(threshold: number): void {
  appState.jaccardThreshold = threshold;
  storeThreshold(threshold);
  if (!appState.clusterSourcePosts.length) return;
  appState.lastNearDup = recomputeNearDuplicatesReport(
    appState.clusterSourcePosts,
    threshold,
    appState.lastNearDup
  );
  setInvestigationPosts(applyClusterTagsToPosts(appState.clusterSourcePosts, appState.lastNearDup));
  const fuzzyHost = document.getElementById("fuzzy-clusters-host");
  if (fuzzyHost) renderFuzzyClusters(fuzzyHost, appState.lastNearDup, { pulse: true });
  updateFuzzyThresholdBadge(threshold, appState.lastNearDup.cross_author_fuzzy_count ?? 0);
  syncJaccardThresholdHud(threshold, resolveThresholdBounds(appState.lastNearDup));
  updatePostsPanel();
}

function updatePostsPanel(): void {
  const host = document.getElementById("post-list-host");
  const countEl = document.getElementById("post-list-count");
  if (!host) return;

  const filtered = filterPosts();
  const active = getInvestigationFilter();
  host.innerHTML = renderPostsList(filtered, {
    limit: appState.postListLimit,
    activeAuthorId: active.authorId,
    blurSensitive: appState.blurSensitive,
    nearDup: appState.lastNearDup,
    groupAuthors: appState.groupAuthorPosts,
  });
  bindPostListAuthorLinks(host);
  const loadMore = document.getElementById("load-more-posts");
  const canLoadMore =
    filtered.length > appState.postListLimit && appState.postListLimit < POST_LIST_MAX;
  if (loadMore) {
    if (canLoadMore) {
      loadMore.removeAttribute("hidden");
      loadMore.textContent = `Show more posts (${Math.min(POST_LIST_MAX, filtered.length) - appState.postListLimit} more)`;
    } else {
      loadMore.setAttribute("hidden", "");
    }
  }
  const shown = Math.min(appState.postListLimit, filtered.length);
  if (countEl) {
    if (hasActiveFilter()) {
      countEl.textContent = `Showing ${shown} of ${filtered.length} matching (${appState.totalNarrativePosts} in narrative)`;
    } else if (filtered.length > POST_LIST_MAX && shown >= POST_LIST_MAX) {
      countEl.textContent = `Showing ${shown} of ${appState.totalNarrativePosts} (capped — export Briefing for full summary)`;
    } else {
      countEl.textContent = `Showing ${shown} of ${appState.totalNarrativePosts} by outrage`;
    }
  }
  refreshDeskStrip();
}

function applyInvestigation(authorId: string | null): void {
  focusPropagationAuthor(authorId);
  updatePostsPanel();
  const f = getInvestigationFilter();
  if (f.authorId && appState.lastLoadedPosts.length) {
    const label = f.label ?? f.authorId.slice(0, 12);
    setInspectorContext(
      label,
      renderAuthorInspector(f.authorId, label, appState.lastLoadedPosts, appState.lastGraphEdgeCount)
    );
    bindInspectorViewAuthor(() => {
      switchDeskMode("evidence", { scroll: false });
      scrollGlobalInvestigationIntoView();
    });
  } else if (!f.postIds?.length && !f.date && !f.escalationTier) {
    resetInspectorEmpty();
  }
  if (hasActiveFilter()) {
    switchDeskMode("evidence", { scroll: false });
    scrollGlobalInvestigationIntoView();
  }
}

function bindGlobalInvestigationChrome(): void {
  bindGlobalInvestigationClear(
    () => {
      clearThemeCardSelection();
      clearInvestigationFilter();
      resetInspectorEmpty();
    },
    () => switchDeskMode("evidence", { scroll: false })
  );
}

function bindInvestigationChrome(): void {
  const clearBtn = document.getElementById("clear-investigation");
  clearBtn?.addEventListener("click", () => {
    clearThemeCardSelection();
    clearInvestigationFilter();
    resetInspectorEmpty();
  });
  bindGlobalInvestigationChrome();
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
    return stateEmptyHtml(
      "No exact duplicate-text clusters",
      "Need ≥2 posts with identical normalized text."
    );
  }
  return clusters
    .slice(0, max)
    .map((c) => {
      const burst = c.burst_synchronized
        ? `<span class="burst-tag" title="Synchronized burst">Burst · ${c.burst_author_count ?? c.author_count} authors in 90s</span>`
        : "";
      const timing =
        c.min_inter_arrival_seconds != null
          ? ` · min gap ${c.min_inter_arrival_seconds}s · span ${c.cluster_span_seconds ?? "?"}s`
          : "";
      const ids = c.post_ids.join(",");
      return `<button type="button" class="cluster cluster-btn${c.burst_synchronized ? " cluster-burst" : ""}" data-post-ids="${ids}" data-burst="${c.burst_synchronized ? "1" : "0"}" aria-label="Duplicate cluster, ${c.count} posts, ${c.author_count} authors">
        <strong>${c.count} posts</strong> · ${c.author_count} authors${burst}
        <p class="post-text">${escapeHtml(truncate(c.sample_text, 200))}</p>
        <p class="post-meta">authors: ${escapeHtml(c.author_ids.slice(0, 5).join(", "))}${c.author_ids.length > 5 ? "…" : ""}${timing}</p>
        <span class="cluster-cta">View ${c.count} posts →</span>
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

function cibSnapshotHtml(cib: CibReport): string {
  const textSignals = cib.text_signals ?? [];
  const graphSignals = cib.graph_signals ?? [];
  const fallbackSignals = cib.signals.slice(0, 3);

  const sparseGraphNote = cib.graph_sufficient
    ? ""
    : `<p class="chart-caption provenance-warn">Propagation graph is sparse (${cib.graph_coverage_pct}% author coverage, ${cib.edge_count} edges). Graph coordination reads near zero — rely on text coordination and duplicate clusters.</p>`;

  const textBlock =
    textSignals.length > 0
      ? `<h3 class="signal-subhead">Text coordination</h3><ul class="signal-list signal-list-compact">${textSignals
          .slice(0, 4)
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("")}</ul>`
      : "";

  const graphBlock =
    graphSignals.length > 0
      ? `<h3 class="signal-subhead">Graph coordination</h3><ul class="signal-list signal-list-compact">${graphSignals
          .slice(0, 4)
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("")}</ul>`
      : "";

  const legacyBlock =
    !textBlock && !graphBlock && fallbackSignals.length
      ? `<ul class="signal-list signal-list-compact">${fallbackSignals
          .map((s) => `<li>${escapeHtml(s)}</li>`)
          .join("")}</ul>`
      : "";

  const body =
    sparseGraphNote || textBlock || graphBlock || legacyBlock
      ? `${sparseGraphNote}${textBlock}${graphBlock}${legacyBlock}`
      : "<p class='empty'>No elevated coordination signals.</p>";

  return `
    <section class="panel panel-cib-snapshot">
      <h2>Coordination at a glance</h2>
      <p class="chart-caption">Text index ${cib.text_coordination_score.toFixed(2)} · graph ${cib.graph_suspicion_score.toFixed(2)} · combined ${cib.suspicion_score.toFixed(2)} (organic ${cib.organic_score.toFixed(2)})</p>
      ${body}
      ${
        cib.iu_astroturf
          ? `<p class="metric-sub">IU astroturf: ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors</p>`
          : ""
      }
    </section>
  `;
}

function deskModeHiddenAttr(mode: DeskMode): string {
  return mode === appState.currentDeskMode ? "" : " hidden";
}

function bindClusterButtons(): void {
  document.querySelectorAll<HTMLButtonElement>(".cluster-btn:not(.fuzzy-cluster-btn)").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ids = (btn.dataset.postIds ?? "")
        .split(",")
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isFinite(n));
      const burst = btn.dataset.burst === "1";
      const sample = btn.querySelector(".post-text")?.textContent ?? "cluster";
      const cluster = appState.lastAmpClusters.find(
        (c) => c.post_ids.length === ids.length && c.post_ids.every((id) => ids.includes(id))
      );
      if (cluster) {
        const parentTheme = findParentThemeLabel(ids, appState.lastThemesReport?.clusters ?? []);
        setInspectorContext(
          burst ? "Synchronized burst" : "Duplicate cluster",
          renderDuplicateClusterInspector(cluster, "exact", parentTheme)
        );
        bindInspectorViewCluster(() => {
          selectDuplicateCluster(sample.slice(0, 40), ids, burst);
          switchDeskMode("evidence", { scroll: false });
          scrollGlobalInvestigationIntoView();
        });
      } else {
        selectDuplicateCluster(sample.slice(0, 40), ids, burst);
        switchDeskMode("evidence", { scroll: false });
        scrollGlobalInvestigationIntoView();
      }
    });
  });
}

function bindAlertInbox(): void {
  document.querySelectorAll<HTMLButtonElement>(".alert-inbox-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.alertAction;
      if (action === "signals") {
        switchDeskMode("pulse");
        return;
      }
      if (action === "anomalies") {
        switchDeskMode("network");
        return;
      }
      const kind = btn.dataset.alertKind;
      if (kind === "theme") {
        const ids = (btn.dataset.postIds ?? "")
          .split(",")
          .map((s) => parseInt(s, 10))
          .filter((n) => Number.isFinite(n));
        const label = btn.dataset.themeLabel ?? "theme cluster";
        selectThemeCluster(label, ids);
      } else if (kind === "cluster") {
        const ids = (btn.dataset.postIds ?? "")
          .split(",")
          .map((s) => parseInt(s, 10))
          .filter((n) => Number.isFinite(n));
        const burst = btn.dataset.burst === "1";
        const label = btn.dataset.clusterLabel ?? "cluster";
        selectDuplicateCluster(label, ids, burst);
      }
      switchDeskMode("evidence", { scroll: false });
      scrollGlobalInvestigationIntoView();
    });
  });
}

function bindPostToolbar(): void {
  document.getElementById("time-range-select")?.addEventListener("change", (e) => {
    const v = (e.target as HTMLSelectElement).value;
    setHoursBack(v ? parseInt(v, 10) : null);
  });
  document.getElementById("blur-sensitive-toggle")?.addEventListener("change", (e) => {
    appState.blurSensitive = (e.target as HTMLInputElement).checked;
    localStorage.setItem(BLUR_SENSITIVE_KEY, appState.blurSensitive ? "1" : "0");
    updatePostsPanel();
  });
  document.getElementById("group-authors-toggle")?.addEventListener("change", (e) => {
    appState.groupAuthorPosts = (e.target as HTMLInputElement).checked;
    updatePostsPanel();
  });
  document.getElementById("compact-charts-toggle")?.addEventListener("change", (e) => {
    appState.compactCharts = (e.target as HTMLInputElement).checked;
    localStorage.setItem(COMPACT_CHARTS_KEY, appState.compactCharts ? "1" : "0");
    applyChartDensity();
  });
  document.getElementById("load-more-posts")?.addEventListener("click", () => {
    appState.postListLimit = POST_LIST_MAX;
    updatePostsPanel();
  });
  document.querySelectorAll<HTMLButtonElement>(".tier-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tier = btn.dataset.tier || null;
      selectEscalationTier(tier, tier ? `Tier: ${tier.replace(/_/g, " ")}` : undefined);
      document.querySelectorAll(".tier-filter").forEach((b) => b.classList.remove("tier-filter-active"));
      btn.classList.add("tier-filter-active");
    });
  });
}

function refreshBriefPanel(): void {
  const host = document.getElementById("brief-content");
  if (!host || !appState.briefContext) return;
  renderBrief(
    host,
    appState.briefContext.narrative,
    appState.briefContext.posts,
    appState.briefContext.cib,
    appState.briefContext.amp,
    appState.briefContext.themes,
    appState.lastNearDup,
    appState.briefContext.crossPollination ?? null,
    appState.briefContext.brief
  );
}

function switchTab(tab: AppTab): void {
  appState.currentTab = tab;
  setTabInUrl(tab);
  showTabPanel(tab);
  if (tab === "brief") refreshBriefPanel();
}

function showMissingSnapshot(message: string): void {
  root.innerHTML = renderMissingSnapshot(message, DATA_LINKS.publishDocs);
}

async function loadDashboard(narrativeId: number): Promise<void> {
  const content = document.getElementById("content");
  if (!content) return;
  content.innerHTML = `<div class="dashboard-skeleton">${stateLoadingHtml("Loading narrative data…")}</div>`;

  try {
    const narratives = await listNarratives();
    const narrativeMeta = narratives.find((n) => n.id === narrativeId);
    const [posts, cib, sentiment, amp, graph, themes, nearDup, benchmark, crossPollination, pollinationHits, provenance, brief] =
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
        fetchProvenance(narrativeId),
        fetchBrief(narrativeId),
      ]);
    appState.clusterSourcePosts = posts;
    const bounds = resolveThresholdBounds(nearDup);
    appState.jaccardThreshold = loadStoredThreshold(
      bounds.defaultThreshold,
      bounds.min,
      bounds.max
    );
    appState.lastNearDup = recomputeNearDuplicatesReport(posts, appState.jaccardThreshold, nearDup);
    appState.lastAmpClusters = amp.clusters;
    appState.lastThemesReport = themes;
    setCoordinationContext({ amp, nearDup: appState.lastNearDup, posts, themes: themes.clusters });
    setInvestigationPosts(applyClusterTagsToPosts(posts, appState.lastNearDup));
    if (narrativeMeta) {
      appState.briefContext = {
        narrative: narrativeMeta,
        posts,
        cib,
        amp,
        themes,
        crossPollination,
        brief,
      };
      resetBriefClipboardBinding();
      refreshBriefPanel();
    }

    const scored = posts.filter((p) => p.outrage_index != null);
    const outrageVals = scored.map((p) => p.outrage_index as number);
    const authors = new Set(posts.map((p) => p.author_id));
    const avg = mean(outrageVals);
    const outrageDiag = computeOutrageDiagnostics(posts, sentiment.buckets);
    const priorityPoints = buildAuthorPriorityPoints(graph, cib, posts);
    const criticalCount = priorityPoints.filter((p) => p.critical).length;
    const fuzzyCount = appState.lastNearDup?.cross_author_fuzzy_count ?? 0;
    const crossActorCount = crossPollination?.actor_count ?? 0;
    const dupCount = amp.clusters.length;
    appState.totalNarrativePosts = posts.length;
    appState.lastCriticalCount = criticalCount;
    appState.lastAnomalyCount = dupCount + fuzzyCount + crossActorCount;

    appState.lastLoadedPosts = posts;
    appState.lastGraphEdgeCount = graph.edges.length;

    const alertRows = [
      ...buildSentimentAlerts(sentiment),
      ...buildAlertRows(amp, cib, appState.lastNearDup, crossPollination, themes),
    ];
    const emergingCount = themes.emerging_theme_count ?? 0;
    const distinctCount = themes.distinct_theme_count ?? themes.cluster_count ?? 0;
    const modeBadges: ModeBadges = {
      pulse: criticalCount || undefined,
      frames: emergingCount || distinctCount || undefined,
      network: appState.lastAnomalyCount || undefined,
      evidence: appState.totalNarrativePosts,
    };

    appState.postListLimit = POST_LIST_INITIAL;
    appState.chartsMounted.pulse = false;
    appState.chartsMounted.frames = false;
    appState.chartsMounted.network = false;

    const modePanels = `
      <section class="desk-mode-panel" data-desk-mode-panel="pulse"${deskModeHiddenAttr("pulse")}>
        <div class="desk-mode-header">
          <h2 class="desk-mode-title">Pulse</h2>
          <p class="desk-mode-desc">Alerts, volume trends, and coordination signals at a glance</p>
        </div>
        <div class="pulse-primary-grid">
          ${renderAlertInboxHtml(alertRows)}
          <div class="metrics-histogram-row">
            ${buildMetricsGrid(posts, authors, avg, cib, provenance)}
            <section class="panel panel-histogram-compact">
              <h2>Outrage distribution</h2>
              ${renderHistogram(posts)}
            </section>
          </div>
          ${metricsTrendPanelHtml(getMetricsHistory(), narrativeMeta?.name ?? "narrative")}
          ${sentimentChartPanelHtml(
            escapeHtml(sentiment.trend),
            outrageDiag,
            sentiment.week_over_week?.alert
          )}
          ${cibSnapshotHtml(cib)}
          ${priorityScatterPanelHtml(criticalCount, graph.edges.length, outrageDiag)}
          ${renderProvenancePanelHtml(provenance, cib)}
          <section class="panel panel-pulse-frames-teaser">
            <h2>Theme frames ${emergingThemesBadge(themes)}</h2>
            <p class="chart-caption">${emergingCount} emerging · ${distinctCount} distinct — open Frames for cluster cards.</p>
            <button type="button" class="btn btn-secondary btn-small" data-goto-mode="frames">Frames →</button>
          </section>
        </div>
      </section>

      <section class="desk-mode-panel" data-desk-mode-panel="frames"${deskModeHiddenAttr("frames")}>
        <div class="desk-mode-header">
          <h2 class="desk-mode-title">Frames</h2>
          <p class="desk-mode-desc">Embedding clusters with PMI phrase labels — select a row to inspect in the sidebar</p>
        </div>
        <div class="themes-panel">${emergingThemesPanelHtml(themes, true)}</div>
      </section>

      <section class="desk-mode-panel evidence-mode-panel" data-desk-mode-panel="evidence"${deskModeHiddenAttr("evidence")}>
        <div class="desk-mode-header">
          <h2 class="desk-mode-title">Evidence</h2>
          <p class="desk-mode-desc">Filtered post stream — follows your investigation filter from any mode</p>
        </div>
        <section class="panel posts-panel" id="posts-panel">
          <div class="posts-panel-header">
            <h2>Posts <span class="post-list-count" id="post-list-count"></span></h2>
            <button type="button" id="clear-investigation" class="btn btn-secondary btn-small" hidden>
              Clear filter
            </button>
          </div>
          ${postsPanelCalloutHtml()}
          <div class="sentiment-tier-filters" id="sentiment-tier-filters">
            <span class="filter-label">Escalation tier</span>
            <button type="button" class="btn btn-secondary btn-small tier-filter" data-tier="">All</button>
            <button type="button" class="btn btn-secondary btn-small tier-filter" data-tier="escalating">Escalating</button>
            <button type="button" class="btn btn-secondary btn-small tier-filter" data-tier="high_conflict">High conflict</button>
            <button type="button" class="btn btn-secondary btn-small tier-filter" data-tier="emerging_theme">Emerging theme</button>
          </div>
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

      <section class="desk-mode-panel" data-desk-mode-panel="network"${deskModeHiddenAttr("network")}>
        <div class="desk-mode-header">
          <h2 class="desk-mode-title">Network</h2>
          <p class="desk-mode-desc">Propagation graph, duplicate text, fuzzy amplification, cross-narrative actors</p>
        </div>
        ${graphPanelHtml()}
        ${panelRollupHtml(
          `Exact duplicate text (${dupCount} cluster${dupCount === 1 ? "" : "s"})`,
          `<div class="panel panel-duplicates">${renderDuplicatesInner(amp.clusters)}</div>`
        )}
        ${panelRollupHtml(
          `Cross-author fuzzy amplification (${fuzzyCount} cluster${fuzzyCount === 1 ? "" : "s"})`,
          fuzzyAmplificationPanelHtml(nearDup, appState.jaccardThreshold, bounds, true)
        )}
        ${panelRollupHtml(
          `Narrative cross-pollination (${crossActorCount} cross-narrative actor${crossActorCount === 1 ? "" : "s"})`,
          crossPollinationPanelHtml(crossPollination, true)
        )}
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
    `;

    content.innerHTML = deskLayoutHtml(modePanels, appState.currentDeskMode, modeBadges);

    clearInvestigationFilter();
    resetInspectorEmpty();

    const pickAuthor = (authorId: string, label: string) => {
      selectAuthor(authorId, label);
    };

    appState.chartMountFns = {
      mountPulse: () => {
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
        const tierCanvas = document.getElementById(
          "sentiment-tier-chart"
        ) as HTMLCanvasElement | null;
        if (tierCanvas) {
          mountSentimentTierChart(tierCanvas, sentiment.buckets);
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
        const metricsCanvas = document.getElementById(
          "metrics-trend-chart"
        ) as HTMLCanvasElement | null;
        if (metricsCanvas && narrativeMeta) {
          mountMetricsTrendChart(metricsCanvas, getMetricsHistory(), narrativeMeta.name);
        }
      },
      mountFrames: () => {
        const themesHost = document.getElementById("themes-list-host");
        if (themesHost && themesHost.dataset.mounted !== "1") {
          themesHost.dataset.mounted = "1";
          renderEmergingThemesTimeline(themesHost, themes, posts, narrativeId);
        }
      },
      mountNetwork: () => {
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
    };

    const fuzzyHost = document.getElementById("fuzzy-clusters-host");
    if (fuzzyHost) renderFuzzyClusters(fuzzyHost, appState.lastNearDup);
    updateFuzzyThresholdBadge(appState.jaccardThreshold, fuzzyCount);
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

    bindDeskModeNav((mode) => switchDeskMode(mode));
    document.querySelectorAll<HTMLButtonElement>("[data-goto-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.gotoMode as DeskMode;
        if (mode) switchDeskMode(mode);
      });
    });
    bindInvestigationChrome();
    bindClusterButtons();
    bindAlertInbox();
    bindPostToolbar();
    bindFuzzyJaccardHud(applyJaccardThreshold);
    bindBriefPrint();
    bindGraphFullscreen();
    bindPostListAuthorLinks(document.getElementById("post-list-host") ?? document);
    updatePostsPanel();
    ensureChartsMountedForMode(appState.currentDeskMode);
    scrollPageToTop();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    content.innerHTML = stateErrorHtml(
      `Failed to load narrative ${narrativeId}`,
      msg,
      "Try refreshing the snapshot file or picking a different narrative."
    );
    scrollPageToTop();
  }
}

async function reloadSnapshotFromNetwork(narrativeId: number): Promise<void> {
  const refresh = document.getElementById("refresh-btn") as HTMLButtonElement | null;
  const stamp = document.querySelector(".data-badge");
  if (refresh) {
    refresh.disabled = true;
    refresh.textContent = "Refreshing…";
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
        ? `Snapshot · Updated ${escapeHtml(at.slice(0, 19))} UTC (reloaded)`
        : "Snapshot (reloaded)";
    }
    await loadDashboard(narrativeId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const content = document.getElementById("content");
    if (content) {
      content.innerHTML = stateErrorHtml(
        "Refresh failed",
        msg,
        "GitHub Pages may still be deploying after ingest. Wait 1–2 minutes and try again."
      );
    }
  } finally {
    if (refresh) {
      refresh.disabled = false;
      refresh.textContent = "Refresh snapshot file";
    }
  }
}

function bindDashboardControls(narratives: NarrativeSummary[], initialId: number): void {
  let selected = initialId;
  const select = document.getElementById("narrative-select") as HTMLSelectElement;
  const refresh = document.getElementById("refresh-btn");
  const gotoBrief = document.getElementById("goto-brief-btn");

  const run = () => {
    selected = parseInt(select.value, 10);
    setUrlNarrative(selected);
    void loadDashboard(selected);
  };

  select.addEventListener("change", run);
  refresh?.addEventListener("click", () => {
    void reloadSnapshotFromNetwork(selected);
  });
  gotoBrief?.addEventListener("click", () => {
    switchTab("brief");
  });
  run();
}

async function bootstrap(): Promise<void> {
  try {
    await loadSnapshot();
    const narratives = await listNarratives();
    if (narratives.length === 0) {
      showMissingSnapshot("Snapshot has no narratives.");
      return;
    }

    const primaryName = getPrimaryNarrativeName();
    const selected =
      narrativeIdFromUrl() ??
      (primaryName ? narratives.find((n) => n.name === primaryName)?.id : undefined) ??
      narratives[0].id;

    root.innerHTML = shell(narratives, selected, getSnapshotGeneratedAt());
    scrollPageToTop();
    bindTabNav(switchTab);
    bindDashboardControls(narratives, selected);
    bindPostToolbar();
    bindBriefPrint();
    bindOnboardingHint();
    bindMethodologyDrawer();
    bindDeskKeyboard(
      (mode) => switchDeskMode(mode),
      () => {
        clearThemeCardSelection();
        clearInvestigationFilter();
        resetInspectorEmpty();
      }
    );
    showTabPanel(appState.currentTab);
    if (appState.currentTab === "brief") refreshBriefPanel();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    showMissingSnapshot(msg);
  }
}

window.addEventListener("heimdall:goto-evidence", () => {
  if (appState.currentTab === "analysis") {
    switchDeskMode("evidence", { scroll: false });
    scrollGlobalInvestigationIntoView();
  }
});

window.addEventListener("heimdall:goto-posts", () => {
  window.dispatchEvent(new CustomEvent("heimdall:goto-evidence"));
});

void bootstrap();

import { selectThemeCluster } from "./investigation";
import { escapeHtml, labelList, safeText } from "./safe-text";
import { applyThemeOverrides, loadThemeOverrides } from "./theme-overrides";
import type { Post, ThemeCluster, ThemeTimelineEntry, ThemesReport } from "./types";
import { truncate } from "./post-display";
import { stateLoadingHtml } from "./ui-states";

const MAX_VISIBLE_CLUSTERS = 16;

interface ThemeRow {
  cluster_id: number;
  labels: string[];
  title: string;
  post_ids: number[];
  size: number;
  emerging_theme: boolean;
  is_noise: boolean;
  is_market_chatter: boolean;
  market_chatter_rate: number;
  first_seen: string | null;
  last_seen: string | null;
  label_distinctiveness: number;
  quality_score: number;
  confidence_tier: string;
  filter_reason: string | null;
  sample_text: string;
}

let clusterIndex = new Map<number, ThemeRow>();
let showMarketChatter = false;
let showFilteredBuckets = false;
let activeNarrativeId = 0;

function primaryLabel(labels: string[], clusterId: number, isMarket: boolean, filterReason: string | null): string {
  if (filterReason === "promo") return "Promo / link spam";
  if (filterReason === "short") return "Ultra-short posts";
  if (filterReason === "non_english") return "Non-English / mixed";
  if (filterReason === "off_topic") return "Off-narrative";
  if (isMarket) return "Market / crypto chatter";
  if (labels.length > 0) return labels[0];
  return `cluster ${clusterId}`;
}

function isFilteredBucket(row: { is_market_chatter?: boolean; filter_reason?: string | null }): boolean {
  return Boolean(row.is_market_chatter || row.filter_reason);
}

function displayLabels(entry: {
  label_phrases?: string[];
  label_terms?: string[];
}): string[] {
  const terms = labelList(entry.label_terms);
  const phrases = labelList(entry.label_phrases);
  const primary = terms[0] ?? phrases[0] ?? "";
  const tail = [
    ...phrases.filter((p) => p !== primary),
    ...terms.slice(1).filter((t) => t !== primary && !phrases.includes(t)),
  ];
  if (primary) return [primary, ...tail].slice(0, 6);
  return tail.slice(0, 6);
}

function normalizeRow(
  entry: ThemeTimelineEntry | ThemeCluster,
  clusters: ThemeCluster[]
): ThemeRow {
  const labels = displayLabels(entry);
  const cluster = clusters.find((c) => c.cluster_id === entry.cluster_id);
  const isMarket = Boolean(entry.is_market_chatter ?? cluster?.is_market_chatter);
  const filterReason = entry.filter_reason ?? cluster?.filter_reason ?? null;
  return {
    cluster_id: entry.cluster_id,
    labels,
    title: primaryLabel(labels, entry.cluster_id, isMarket, filterReason),
    post_ids: entry.post_ids ?? cluster?.post_ids ?? [],
    size: entry.size ?? cluster?.size ?? entry.post_ids?.length ?? 0,
    emerging_theme: Boolean(entry.emerging_theme),
    is_noise: Boolean(entry.is_noise),
    is_market_chatter: isMarket,
    market_chatter_rate: entry.market_chatter_rate ?? cluster?.market_chatter_rate ?? 0,
    first_seen: entry.first_seen ?? cluster?.first_seen ?? null,
    last_seen: entry.last_seen ?? cluster?.last_seen ?? null,
    label_distinctiveness: entry.label_distinctiveness ?? cluster?.label_distinctiveness ?? 0,
    quality_score: entry.quality_score ?? cluster?.quality_score ?? 0,
    confidence_tier: entry.confidence_tier ?? cluster?.confidence_tier ?? "medium",
    filter_reason: filterReason,
    sample_text: cluster?.sample_text ?? "",
  };
}

function normalizeThemes(report: ThemesReport, includeFiltered: boolean): ThemeRow[] {
  const overridden = applyThemeOverrides(report.clusters ?? [], loadThemeOverrides(activeNarrativeId));
  const clusters = overridden;
  const source = report.timeline?.length
    ? [...report.timeline, ...clusters.filter((c) => c.is_market_chatter)]
    : clusters.filter(
        (c) =>
          (c.label_distinctiveness ?? 0) >= 0.12 ||
          c.emerging_theme ||
          c.is_noise ||
          c.is_market_chatter
      );

  const seen = new Set<number>();
  const uniqueSource = source.filter((entry) => {
    if (seen.has(entry.cluster_id)) return false;
    seen.add(entry.cluster_id);
    return true;
  });

  const rows = uniqueSource.map((entry) => normalizeRow(entry, clusters));
  const filtered = includeFiltered ? rows : rows.filter((row) => !isFilteredBucket(row));
  filtered.sort((a, b) => {
    if (a.is_market_chatter !== b.is_market_chatter) return a.is_market_chatter ? 1 : -1;
    if (a.emerging_theme !== b.emerging_theme) return a.emerging_theme ? -1 : 1;
    if (a.is_noise !== b.is_noise) return a.is_noise ? 1 : -1;
    return b.size - a.size;
  });
  return filtered;
}

function dateSpan(row: ThemeRow): string {
  if (row.first_seen && row.last_seen) {
    return row.first_seen === row.last_seen
      ? row.first_seen
      : `${row.first_seen} → ${row.last_seen}`;
  }
  return "—";
}

function tierBreakdown(postIds: number[], posts: Post[]): Array<{ tier: string; count: number }> {
  const postMap = new Map(posts.map((p) => [p.id, p]));
  const counts = new Map<string, number>();
  for (const pid of postIds) {
    const tier = postMap.get(pid)?.escalation_tier ?? "unknown";
    counts.set(tier, (counts.get(tier) ?? 0) + 1);
  }
  const order = ["inflammatory", "escalating", "neutral", "unknown"];
  return order
    .map((tier) => ({ tier, count: counts.get(tier) ?? 0 }))
    .filter((row) => row.count > 0);
}

function renderDetail(row: ThemeRow, posts: Post[]): string {
  const tiers = tierBreakdown(row.post_ids, posts);
  const maxTier = Math.max(...tiers.map((t) => t.count), 1);
  const tags = row.labels
    .map((label) => {
      const cls = label.includes(" ") ? "theme-token theme-token-phrase" : "theme-token";
      return `<span class="${cls}">${escapeHtml(label)}</span>`;
    })
    .join("");

  return `
    <div class="theme-detail">
      <div class="theme-detail-header">
        <h3>${escapeHtml(row.title)}</h3>
        <p class="theme-detail-meta">${row.size} posts · ${escapeHtml(dateSpan(row))}${
          row.emerging_theme ? " · <span class='topology-badge topology-star'>emerging</span>" : ""
        }</p>
      </div>
      <div class="theme-detail-tags">${tags || "<span class='theme-token theme-token-empty'>(no labels)</span>"}</div>
      ${
        row.sample_text
          ? `<blockquote class="theme-detail-sample">${escapeHtml(truncate(row.sample_text, 320))}</blockquote>`
          : ""
      }
      ${
        tiers.length
          ? `<div class="theme-tier-breakdown">${tiers
              .map(
                (tier) => `<div class="theme-tier-row">
                  <span class="theme-tier-name">${escapeHtml(tier.tier)}</span>
                  <span class="theme-tier-bar-track"><span class="theme-tier-bar theme-tier-bar-${escapeHtml(tier.tier)}" style="width:${((tier.count / maxTier) * 100).toFixed(1)}%"></span></span>
                  <span class="theme-tier-count">${tier.count}</span>
                </div>`
              )
              .join("")}</div>`
          : ""
      }
      <button type="button" class="btn btn-secondary btn-small theme-detail-cta" data-cluster-id="${row.cluster_id}">
        View ${row.size} posts →
      </button>
    </div>
  `;
}

function renderTable(rows: ThemeRow[], hiddenFilteredCount: number, report: ThemesReport): string {
  const visible = rows.slice(0, MAX_VISIBLE_CLUSTERS);
  const hiddenCount = Math.max(rows.length - visible.length, 0);

  return `
    <table class="theme-table">
      <thead>
        <tr>
          <th scope="col">Cluster</th>
          <th scope="col">Posts</th>
          <th scope="col">Active</th>
          <th scope="col">Signals</th>
        </tr>
      </thead>
      <tbody>
        ${visible
          .map((row) => {
            const distinctPct = Math.round(row.label_distinctiveness * 100);
            const qualityPct = Math.round(row.quality_score * 100);
            const tier = row.confidence_tier || "medium";
            return `<tr
              class="theme-row${row.emerging_theme ? " theme-row-emerging" : ""}${row.is_noise ? " theme-row-noise" : ""}${row.is_market_chatter ? " theme-row-market" : ""}${row.filter_reason ? " theme-row-filtered" : ""}"
              data-cluster-id="${row.cluster_id}"
              tabindex="0"
              role="button"
              aria-label="Theme cluster ${escapeHtml(row.title)}"
            >
              <td class="theme-row-label">
                <span class="theme-row-title">${escapeHtml(row.title)}</span>
                ${
                  row.is_market_chatter
                    ? `<span class="theme-row-sub">Fin-twit / ticker spam · ${Math.round(row.market_chatter_rate * 100)}% market signal</span>`
                    : row.labels.length > 1
                      ? `<span class="theme-row-sub">${escapeHtml(row.labels.slice(1, 3).join(" · "))}</span>`
                      : ""
                }
              </td>
              <td>${row.size}</td>
              <td class="theme-row-dates">${escapeHtml(dateSpan(row))}</td>
              <td class="theme-row-signals">
                ${row.emerging_theme ? `<span class="topology-badge topology-star">emerging</span> ` : ""}
                ${tier === "high" ? `<span class="theme-signal-pill theme-signal-high">high conf</span>` : tier === "low" ? `<span class="theme-signal-pill theme-signal-low">low conf</span>` : ""}
                ${distinctPct > 0 ? `<span class="theme-signal-pill">${distinctPct}% distinct</span>` : ""}
                ${qualityPct > 0 ? `<span class="theme-signal-pill">${qualityPct}% quality</span>` : ""}
              </td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
    ${
      hiddenFilteredCount > 0
        ? `<p class="chart-caption theme-table-footnote">${hiddenFilteredCount} filtered cluster${hiddenFilteredCount === 1 ? "" : "s"} hidden — toggle below to include.</p>`
        : ""
    }
    ${
      hiddenCount > 0
        ? `<p class="chart-caption theme-table-footnote">${hiddenCount} smaller narrative cluster${hiddenCount === 1 ? "" : "s"} hidden (showing top ${MAX_VISIBLE_CLUSTERS}).</p>`
        : ""
    }
  `;
}

function selectRow(host: HTMLElement, detailHost: HTMLElement | null, row: ThemeRow, posts: Post[]): void {
  host.querySelectorAll(".theme-row").forEach((el) => el.classList.remove("theme-row-active"));
  host
    .querySelector(`.theme-row[data-cluster-id="${row.cluster_id}"]`)
    ?.classList.add("theme-row-active");

  if (detailHost) {
    detailHost.innerHTML = renderDetail(row, posts);
    detailHost.querySelector<HTMLButtonElement>(".theme-detail-cta")?.addEventListener("click", () => {
      const label = `[${row.labels.join(", ") || row.title}]`;
      selectThemeCluster(label, row.post_ids);
      window.dispatchEvent(new CustomEvent("heimdall:goto-posts"));
    });
  }
}

function bindTable(host: HTMLElement, detailHost: HTMLElement | null, rows: ThemeRow[], posts: Post[]): void {
  host.querySelectorAll<HTMLElement>(".theme-row").forEach((el) => {
    const clusterId = parseInt(el.dataset.clusterId ?? "", 10);
    const row = clusterIndex.get(clusterId);
    if (!row) return;

    const activate = () => selectRow(host, detailHost, row, posts);
    el.addEventListener("click", activate);
    el.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
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
    ? `<p class="chart-caption provenance-warn">Lexical TF-IDF fallback — treat cluster labels as low confidence until neural embeddings are enabled on export.</p>`
    : "";
  const inner = `
      <h2 class="themes-panel-title">Theme clusters ${badge}</h2>
      <div class="themes-panel-intro">
        ${fallbackNote}
        <p class="chart-caption">
          Embedding clusters with PMI phrase labels. Related clusters merge automatically when
          they share substantive frames (e.g. governor + election fraud). Fin-twit and crypto
          ticker spam is filtered out of clustering by default. Select a row to inspect framing
          and filter posts.
        </p>
        <label class="theme-market-toggle">
          <input type="checkbox" id="theme-show-market" />
          Show filtered buckets (market, promo, off-topic)
        </label>
      </div>
      <div class="theme-workbench">
        <div id="themes-list-host" class="themes-list-host">
          ${stateLoadingHtml("Loading theme clusters…")}
        </div>
        <div id="themes-detail-host" class="themes-detail-host"></div>
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
  posts: Post[] = [],
  narrativeId = 0
): void {
  const meta = document.getElementById("themes-meta");
  const detailHost = document.getElementById("themes-detail-host");
  const marketToggle = document.getElementById("theme-show-market") as HTMLInputElement | null;
  clusterIndex = new Map();
  activeNarrativeId = narrativeId;
  showFilteredBuckets = marketToggle?.checked ?? false;

  if (!report.available) {
    const hint = report.reason?.includes("USE_EMBEDDING_THEMES")
      ? " Re-export with USE_EMBEDDING_THEMES=true when exporting snapshot.json."
      : "";
    host.innerHTML = `<p class="empty">${escapeHtml(report.reason ?? "Theme clustering unavailable in this snapshot.")}${escapeHtml(hint)}</p>`;
    if (detailHost) detailHost.innerHTML = "";
    if (meta) meta.textContent = report.method ? `Method: ${report.method}` : "";
    return;
  }

  const allRows = normalizeThemes(report, true);
  const rows = normalizeThemes(report, showFilteredBuckets);
  const hiddenFilteredCount = showFilteredBuckets
    ? 0
    : allRows.filter((row) => isFilteredBucket(row)).length;

  if (rows.length === 0 && hiddenFilteredCount > 0) {
    host.innerHTML =
      "<p class='empty'>Only filtered buckets detected (market/promo/off-topic) — enable the toggle above to inspect them.</p>";
    if (detailHost) detailHost.innerHTML = "";
    if (meta) {
      meta.textContent = `${hiddenFilteredCount} filtered cluster(s) · ${report.post_count} posts`;
    }
    marketToggle?.addEventListener("change", () => {
      showFilteredBuckets = marketToggle.checked;
      renderEmergingThemesTimeline(host, report, posts, narrativeId);
    });
    return;
  }

  if (rows.length === 0) {
    host.innerHTML =
      "<p class='empty'>No embedding clusters for this narrative (need ≥3 posts and USE_EMBEDDING_THEMES on export).</p>";
    if (detailHost) detailHost.innerHTML = "";
    if (meta) meta.textContent = `Model: ${report.model} · ${report.post_count} posts`;
    return;
  }

  for (const row of allRows) {
    clusterIndex.set(row.cluster_id, row);
  }

  host.innerHTML = renderTable(rows, hiddenFilteredCount, report);
  bindTable(host, detailHost, rows, posts);

  const firstPick =
    rows.find((row) => row.emerging_theme && !isFilteredBucket(row) && !row.is_noise) ??
    rows.find((row) => !isFilteredBucket(row) && !row.is_noise) ??
    rows[0];
  if (firstPick) {
    selectRow(host, detailHost, firstPick, posts);
  }

  marketToggle?.addEventListener("change", () => {
    showFilteredBuckets = marketToggle.checked;
    renderEmergingThemesTimeline(host, report, posts, narrativeId);
  });

  if (meta) {
    const encoder = report.model === "tfidf-fallback" ? "TF-IDF lexical vectors" : safeText(report.model);
    const filteredNote =
      (report.filtered_post_count ?? 0) > 0
        ? ` · ${report.filtered_post_count} posts pre-filtered`
        : "";
    const quality = report.quality_metrics;
    const qualityNote = quality?.silhouette != null ? ` · silhouette ${quality.silhouette}` : "";
    const lineageNote =
      (report.theme_lineage?.length ?? 0) > 0
        ? ` · ${report.theme_lineage?.length} weekly windows`
        : "";
    meta.textContent = `${report.distinct_theme_count ?? report.cluster_count} distinct · ${report.emerging_theme_count} emerging · ${report.method} · ${encoder}${filteredNote}${qualityNote}${lineageNote}`;
  }
}

export function clearThemeCardSelection(): void {
  document.querySelectorAll(".theme-row-active").forEach((el) => {
    el.classList.remove("theme-row-active");
  });
}

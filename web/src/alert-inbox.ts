import { classifyDuplicateCluster, computeThemeCoordination } from "./cluster-coordination";
import type { DeskMode } from "./desk-modes";
import { escapeHtml, truncate } from "./post-display";
import { labelList } from "./safe-text";
import type {
  AmplificationReport,
  CibReport,
  CrossPollinationReport,
  DuplicateCluster,
  NearDuplicatesReport,
  ThemesReport,
} from "./types";

export type AlertSeverity = "critical" | "watch" | "context";

export type AlertKind =
  | "burst"
  | "duplicate"
  | "fuzzy"
  | "cross-pollination"
  | "cib"
  | "theme"
  | "sentiment";

export type AlertCategory = "coordination" | "themes" | "sentiment" | "cross";

export interface AlertRow {
  severity: AlertSeverity;
  category: AlertCategory;
  title: string;
  excerpt: string;
  metric: string;
  count: number;
  postIds: number[];
  burst: boolean;
  kind: AlertKind;
  themeLabel?: string;
  tier?: "high" | "medium" | "low" | "context";
  tierLabel?: string;
  filterDate?: string;
}

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "Critical",
  watch: "Watch",
  context: "Context",
};

const CATEGORY_LABEL: Record<AlertCategory, string> = {
  coordination: "Coordination",
  themes: "Emerging themes",
  sentiment: "Sentiment drift",
  cross: "Cross-narrative",
};

const KIND_LABEL: Record<AlertKind, string> = {
  burst: "Burst",
  duplicate: "Duplicate",
  fuzzy: "Fuzzy",
  cib: "CIB",
  theme: "Theme",
  "cross-pollination": "Cross-narrative",
  sentiment: "Sentiment",
};

const SEVERITY_ORDER: AlertSeverity[] = ["critical", "watch", "context"];
const CATEGORY_ORDER: AlertCategory[] = ["coordination", "sentiment", "themes", "cross"];

function burstClusters(clusters: DuplicateCluster[]): DuplicateCluster[] {
  return clusters.filter((c) => c.burst_synchronized);
}

function exactClusters(clusters: DuplicateCluster[]): DuplicateCluster[] {
  return clusters.filter((c) => !c.burst_synchronized);
}

function postMetric(count: number, authorCount?: number): string {
  const posts = `${count} post${count === 1 ? "" : "s"}`;
  if (authorCount != null && authorCount > 0) {
    return `${posts} · ${authorCount} author${authorCount === 1 ? "" : "s"}`;
  }
  return posts;
}

export function buildAlertRows(
  amp: AmplificationReport,
  cib: CibReport,
  nearDup: NearDuplicatesReport | null,
  crossPollination: CrossPollinationReport | null,
  themes: ThemesReport
): AlertRow[] {
  const rows: AlertRow[] = [];

  for (const c of burstClusters(amp.clusters).slice(0, 5)) {
    const tierInfo = classifyDuplicateCluster(c, "exact");
    rows.push({
      severity: "critical",
      category: "coordination",
      title: "Synchronized burst",
      excerpt: truncate(c.sample_text, 120),
      metric: postMetric(c.count, c.author_count),
      count: c.count,
      postIds: c.post_ids,
      burst: true,
      kind: "burst",
      tier: tierInfo.tier,
      tierLabel: tierInfo.label,
    });
  }

  if (cib.suspicion_score >= 0.65) {
    rows.push({
      severity: "critical",
      category: "coordination",
      title: "Elevated CIB suspicion",
      excerpt: cib.signals[0] ?? `Combined score ${cib.suspicion_score.toFixed(2)}`,
      metric: `${cib.edge_count} edge${cib.edge_count === 1 ? "" : "s"}`,
      count: cib.edge_count,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  if (cib.text_coordination_score >= 0.38) {
    rows.push({
      severity: "watch",
      category: "coordination",
      title: "Text coordination elevated",
      excerpt:
        cib.text_signals?.[0] ??
        `Text index ${cib.text_coordination_score.toFixed(2)} across duplicate signals`,
      metric: `index ${cib.text_coordination_score.toFixed(2)}`,
      count: nearDup?.cross_author_fuzzy_count ?? amp.clusters.length,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  for (const c of (nearDup?.cross_author_fuzzy ?? []).slice(0, 4)) {
    const tierInfo = classifyDuplicateCluster(c, "fuzzy");
    rows.push({
      severity: c.burst_synchronized ? "critical" : "watch",
      category: "coordination",
      title: c.burst_synchronized ? "Fuzzy burst" : "Cross-author fuzzy cluster",
      excerpt: truncate(c.sample_text, 120),
      metric: postMetric(c.count, c.author_count),
      count: c.count,
      postIds: c.post_ids,
      burst: Boolean(c.burst_synchronized),
      kind: "fuzzy",
      tier: tierInfo.tier,
      tierLabel: tierInfo.label,
    });
  }

  for (const c of exactClusters(amp.clusters).slice(0, 3)) {
    const tierInfo = classifyDuplicateCluster(c, "exact");
    rows.push({
      severity: "watch",
      category: "coordination",
      title: "Exact duplicate text",
      excerpt: truncate(c.sample_text, 120),
      metric: postMetric(c.count, c.author_count),
      count: c.count,
      postIds: c.post_ids,
      burst: false,
      kind: "duplicate",
      tier: tierInfo.tier,
      tierLabel: tierInfo.label,
    });
  }

  const crossCount = crossPollination?.actor_count ?? 0;
  if (crossCount > 0) {
    rows.push({
      severity: "watch",
      category: "cross",
      title: "Cross-narrative actors",
      excerpt: "Accounts posting across multiple tracked narratives in this snapshot.",
      metric: `${crossCount} account${crossCount === 1 ? "" : "s"}`,
      count: crossCount,
      postIds: [],
      burst: false,
      kind: "cross-pollination",
    });
  }

  const emerging = (themes.timeline ?? themes.clusters).filter((t) => t.emerging_theme).slice(0, 3);
  const themeLowConfidence = (themes.model ?? "").toLowerCase().includes("tfidf");
  for (const t of emerging) {
    const phrases = labelList(t.label_phrases);
    const terms = phrases.length ? phrases : labelList(t.label_terms);
    const label = terms.slice(0, 4).join(" · ") || `cluster ${t.cluster_id}`;
    const fullCluster = themes.clusters.find((c) => c.cluster_id === t.cluster_id);
    const overlay = computeThemeCoordination(t.post_ids ?? [], [], fullCluster);
    rows.push({
      severity: themeLowConfidence ? "context" : overlay.tier === "high" ? "watch" : "context",
      category: "themes",
      title: themeLowConfidence ? "Theme cluster (lexical fallback)" : "Emerging theme",
      excerpt: label,
      metric: postMetric(t.size ?? t.post_ids?.length ?? 0),
      count: t.size ?? t.post_ids?.length ?? 0,
      postIds: t.post_ids ?? [],
      burst: false,
      kind: "theme",
      themeLabel: label,
      tier: overlay.tier,
      tierLabel: overlay.tier_label,
    });
  }

  return rows.sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
      CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );
}

function severitySummary(rows: AlertRow[]): Record<AlertSeverity, number> {
  return rows.reduce(
    (acc, row) => {
      acc[row.severity] += 1;
      return acc;
    },
    { critical: 0, watch: 0, context: 0 } as Record<AlertSeverity, number>
  );
}

function groupByCategory(rows: AlertRow[]): Map<AlertCategory, AlertRow[]> {
  const groups = new Map<AlertCategory, AlertRow[]>();
  for (const cat of CATEGORY_ORDER) groups.set(cat, []);
  for (const row of rows) {
    groups.get(row.category)?.push(row);
  }
  return groups;
}

function actionLabel(row: AlertRow): string {
  if (row.postIds.length > 0) return "Evidence";
  if (row.kind === "cross-pollination") return "Network";
  if (row.kind === "theme") return "Frames";
  if (row.kind === "sentiment" && row.filterDate) return "Filter day";
  if (row.kind === "sentiment") return "Chart";
  if (row.kind === "cib") return "Signals";
  return "Open";
}

function rowDataAttrs(row: AlertRow): string {
  const parts = [
    `data-alert-kind="${row.kind}"`,
    `data-alert-severity="${row.severity}"`,
    `data-alert-category="${row.category}"`,
  ];
  if (row.postIds.length) parts.push(`data-post-ids="${row.postIds.join(",")}"`);
  if (row.burst) parts.push(`data-burst="1"`);
  if (row.themeLabel) parts.push(`data-theme-label="${escapeHtml(row.themeLabel)}"`);
  if (row.filterDate) parts.push(`data-filter-date="${escapeHtml(row.filterDate)}"`);
  if (row.kind === "cross-pollination") parts.push(`data-alert-action="network"`);
  if (row.kind === "cib") parts.push(`data-alert-action="cib-signals"`);
  if (row.kind === "sentiment" && !row.filterDate) parts.push(`data-alert-action="sentiment-chart"`);
  if (row.kind === "theme") parts.push(`data-alert-action="frames"`);
  if (row.postIds.length) parts.push(`data-cluster-label="${escapeHtml(row.excerpt.slice(0, 48))}"`);
  return parts.join(" ");
}

function renderAlertCard(row: AlertRow): string {
  const tierBadge = row.tierLabel
    ? `<span class="coord-tier-badge coord-tier-${row.tier ?? "context"}">${escapeHtml(row.tierLabel)}</span>`
    : "";
  return `<li class="alert-inbox-item">
    <button type="button" class="alert-inbox-card alert-inbox-${row.severity}" ${rowDataAttrs(row)}>
      <span class="alert-severity-dot" aria-hidden="true" title="${SEVERITY_LABEL[row.severity]}"></span>
      <div class="alert-card-body">
        <div class="alert-card-meta">
          <span class="alert-kind-pill">${escapeHtml(KIND_LABEL[row.kind])}</span>
          ${tierBadge}
          <span class="alert-card-metric">${escapeHtml(row.metric)}</span>
        </div>
        <strong class="alert-card-title">${escapeHtml(row.title)}</strong>
        <p class="alert-card-excerpt">${escapeHtml(row.excerpt)}</p>
      </div>
      <span class="alert-card-action">${escapeHtml(actionLabel(row))} →</span>
    </button>
  </li>`;
}

function renderSummaryChips(summary: Record<AlertSeverity, number>): string {
  const chips = SEVERITY_ORDER.filter((s) => summary[s] > 0).map(
    (s) =>
      `<span class="alert-summary-chip alert-summary-${s}">${summary[s]} ${SEVERITY_LABEL[s]}</span>`
  );
  return chips.length ? `<div class="alert-inbox-summary">${chips.join("")}</div>` : "";
}

export function renderAlertInboxHtml(rows: AlertRow[]): string {
  if (rows.length === 0) {
    return `<section class="panel panel-alert-inbox panel-alert-inbox-empty">
      <header class="alert-inbox-header">
        <h2>Alert inbox</h2>
      </header>
      <div class="alert-inbox-empty-state">
        <p class="alert-inbox-empty-title">No elevated signals</p>
        <p class="chart-caption">Nothing crossed coordination or sentiment thresholds in this snapshot. Check metrics below or browse Evidence for the full post stream.</p>
      </div>
    </section>`;
  }

  const summary = severitySummary(rows);
  const groups = groupByCategory(rows);
  const groupHtml = CATEGORY_ORDER.map((cat) => {
    const items = groups.get(cat) ?? [];
    if (!items.length) return "";
    return `<div class="alert-inbox-group" data-alert-group="${cat}">
      <h3 class="alert-inbox-group-title">${CATEGORY_LABEL[cat]}</h3>
      <ul class="alert-inbox-list">${items.map(renderAlertCard).join("")}</ul>
    </div>`;
  }).join("");

  return `<section class="panel panel-alert-inbox">
    <header class="alert-inbox-header">
      <div class="alert-inbox-header-text">
        <h2>Alert inbox</h2>
        <p class="chart-caption">Prioritized signals — select a card to investigate.</p>
      </div>
      ${renderSummaryChips(summary)}
    </header>
    <div class="alert-inbox-groups">${groupHtml}</div>
  </section>`;
}

export type AlertInboxHandlers = {
  switchDeskMode: (mode: DeskMode, options?: { scroll?: boolean }) => void;
  scrollInvestigationIntoView: () => void;
  selectThemeCluster: (label: string, postIds: number[]) => void;
  selectDuplicateCluster: (label: string, postIds: number[], burst: boolean) => void;
  selectDate: (date: string) => void;
  scrollToElement: (id: string) => void;
};

function parsePostIds(raw: string | undefined): number[] {
  return (raw ?? "")
    .split(",")
    .map((s) => parseInt(s, 10))
    .filter((n) => Number.isFinite(n));
}

export function bindAlertInbox(handlers: AlertInboxHandlers): void {
  document.querySelectorAll<HTMLButtonElement>(".alert-inbox-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.alertAction;
      const kind = btn.dataset.alertKind;
      const filterDate = btn.dataset.filterDate;

      if (action === "network") {
        handlers.switchDeskMode("network");
        return;
      }
      if (action === "cib-signals") {
        handlers.scrollToElement("panel-cib-snapshot");
        return;
      }
      if (action === "sentiment-chart") {
        handlers.scrollToElement("sentiment-timeline-chart");
        return;
      }
      if (action === "frames" && kind === "theme") {
        const ids = parsePostIds(btn.dataset.postIds);
        const label = btn.dataset.themeLabel ?? "theme cluster";
        handlers.selectThemeCluster(label, ids);
        handlers.switchDeskMode("frames", { scroll: false });
        return;
      }
      if (filterDate) {
        handlers.selectDate(filterDate);
        handlers.switchDeskMode("evidence", { scroll: false });
        handlers.scrollInvestigationIntoView();
        return;
      }
      if (kind === "theme") {
        const ids = parsePostIds(btn.dataset.postIds);
        handlers.selectThemeCluster(btn.dataset.themeLabel ?? "theme cluster", ids);
      } else if (kind === "cluster" || kind === "burst" || kind === "duplicate" || kind === "fuzzy") {
        const ids = parsePostIds(btn.dataset.postIds);
        const burst = btn.dataset.burst === "1";
        const label = btn.dataset.clusterLabel ?? "cluster";
        handlers.selectDuplicateCluster(label, ids, burst);
      }
      if (parsePostIds(btn.dataset.postIds).length > 0) {
        handlers.switchDeskMode("evidence", { scroll: false });
        handlers.scrollInvestigationIntoView();
      }
    });
  });
}

import { escapeHtml, truncate } from "./post-display";
import type {
  AmplificationReport,
  CibReport,
  CrossPollinationReport,
  DuplicateCluster,
  NearDuplicatesReport,
  ThemesReport,
} from "./types";

export type AlertSeverity = "critical" | "watch" | "context";

export interface AlertRow {
  severity: AlertSeverity;
  title: string;
  detail: string;
  count: number;
  postIds: number[];
  burst: boolean;
  kind: "burst" | "duplicate" | "fuzzy" | "cross-pollination" | "cib" | "theme";
  themeLabel?: string;
}

function burstClusters(clusters: DuplicateCluster[]): DuplicateCluster[] {
  return clusters.filter((c) => c.burst_synchronized);
}

function exactClusters(clusters: DuplicateCluster[]): DuplicateCluster[] {
  return clusters.filter((c) => !c.burst_synchronized);
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
    rows.push({
      severity: "critical",
      title: "Synchronized burst",
      detail: truncate(c.sample_text, 120),
      count: c.count,
      postIds: c.post_ids,
      burst: true,
      kind: "burst",
    });
  }

  if (cib.text_coordination_score >= 0.38) {
    rows.push({
      severity: "watch",
      title: "Text coordination",
      detail:
        cib.text_signals?.[0] ??
        `Text index ${cib.text_coordination_score.toFixed(2)} · ${cib.signals.length} signal(s)`,
      count: nearDup?.cross_author_fuzzy_count ?? amp.clusters.length,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  if (cib.suspicion_score >= 0.65) {
    rows.push({
      severity: "critical",
      title: "Elevated CIB suspicion",
      detail: cib.signals[0] ?? `Score ${cib.suspicion_score.toFixed(2)} · ${cib.edge_count} edges`,
      count: cib.edge_count,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  for (const c of (nearDup?.cross_author_fuzzy ?? []).slice(0, 4)) {
    rows.push({
      severity: "watch",
      title: c.burst_synchronized ? "Fuzzy burst" : "Cross-author fuzzy cluster",
      detail: truncate(c.sample_text, 120),
      count: c.count,
      postIds: c.post_ids,
      burst: Boolean(c.burst_synchronized),
      kind: "fuzzy",
    });
  }

  for (const c of exactClusters(amp.clusters).slice(0, 3)) {
    rows.push({
      severity: "watch",
      title: "Exact duplicate text",
      detail: truncate(c.sample_text, 120),
      count: c.count,
      postIds: c.post_ids,
      burst: false,
      kind: "duplicate",
    });
  }

  const crossCount = crossPollination?.actor_count ?? 0;
  if (crossCount > 0) {
    rows.push({
      severity: "watch",
      title: "Cross-narrative actors",
      detail: `${crossCount} account${crossCount === 1 ? "" : "s"} appear in multiple narratives`,
      count: crossCount,
      postIds: [],
      burst: false,
      kind: "cross-pollination",
    });
  }

  const emerging = (themes.timeline ?? themes.clusters).filter((t) => t.emerging_theme).slice(0, 3);
  const themeLowConfidence = (themes.model ?? "").toLowerCase().includes("tfidf");
  for (const t of emerging) {
    const terms = (t.label_terms ?? []).slice(0, 4).join(" · ") || `cluster ${t.cluster_id}`;
    rows.push({
      severity: themeLowConfidence ? "context" : "context",
      title: themeLowConfidence ? "Theme cluster (lexical fallback)" : "Emerging theme",
      detail: terms,
      count: t.size ?? t.post_ids?.length ?? 0,
      postIds: t.post_ids ?? [],
      burst: false,
      kind: "theme",
      themeLabel: terms,
    });
  }

  const order: AlertSeverity[] = ["critical", "watch", "context"];
  return rows.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
}

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "Critical",
  watch: "Watch",
  context: "Context",
};

export function renderAlertInboxHtml(rows: AlertRow[]): string {
  if (rows.length === 0) {
    return `<section class="panel panel-alert-inbox">
      <h2>Alert inbox</h2>
      <p class="state-empty">No elevated signals in this snapshot. Scan sentiment and posts for context.</p>
    </section>`;
  }

  const items = rows
    .map((row) => {
      const cta =
        row.kind === "cib"
          ? `<span class="alert-inbox-cta">Open Signals →</span>`
          : row.kind === "cross-pollination"
            ? `<span class="alert-inbox-cta">Open Anomalies →</span>`
            : row.postIds.length
              ? `<span class="alert-inbox-cta">View ${row.count} posts →</span>`
              : "";
      const dataAttrs =
        row.kind === "cib"
          ? `data-alert-action="signals"`
          : row.kind === "cross-pollination"
            ? `data-alert-action="anomalies"`
            : row.kind === "theme"
              ? `data-alert-kind="theme" data-post-ids="${row.postIds.join(",")}" data-theme-label="${escapeHtml(row.themeLabel ?? row.detail)}"`
              : `data-alert-kind="cluster" data-post-ids="${row.postIds.join(",")}" data-burst="${row.burst ? "1" : "0"}" data-cluster-label="${escapeHtml(row.detail.slice(0, 40))}"`;

      return `<li class="alert-inbox-row alert-inbox-${row.severity}">
        <span class="alert-inbox-severity" aria-label="${SEVERITY_LABEL[row.severity]}">${SEVERITY_LABEL[row.severity]}</span>
        <div class="alert-inbox-body">
          <strong class="alert-inbox-title">${escapeHtml(row.title)}</strong>
          <span class="alert-inbox-count">${row.count}</span>
          <p class="alert-inbox-detail">${escapeHtml(row.detail)}</p>
        </div>
        <button type="button" class="alert-inbox-btn btn btn-secondary btn-small" ${dataAttrs}>
          Investigate →
          ${cta}
        </button>
      </li>`;
    })
    .join("");

  return `<section class="panel panel-alert-inbox">
    <h2>Alert inbox</h2>
    <p class="chart-caption">Prioritized signals — click <strong>Investigate</strong> to filter posts or jump to a section.</p>
    <ul class="alert-inbox-list">${items}</ul>
  </section>`;
}

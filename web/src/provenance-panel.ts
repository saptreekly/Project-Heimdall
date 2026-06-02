import { escapeHtml } from "./post-display";
import type { CibReport, NarrativeProvenance } from "./types";

function cibField(cib: CibReport, key: keyof CibReport, fallback = 0): number {
  const v = cib[key];
  return typeof v === "number" ? v : fallback;
}

export function renderProvenancePanelHtml(
  provenance: NarrativeProvenance | null | undefined,
  cib: CibReport
): string {
  if (!provenance) return "";

  const textScore = cibField(cib, "text_coordination_score");
  const graphScore = cibField(cib, "graph_suspicion_score");
  const graphSufficient = Boolean(cib.graph_sufficient);

  const truncated = provenance.posts_truncated
    ? ` · showing latest ${provenance.posts_in_snapshot} of ${provenance.posts_total_db}`
    : ` · ${provenance.posts_in_snapshot} posts (full narrative)`;

  const graphNote = graphSufficient
    ? `${provenance.graph_coverage_pct}% authors connected · ${provenance.graph_edge_count} edges`
    : `Graph sparse (${provenance.graph_edge_count} edges, ${provenance.graph_coverage_pct}% coverage) — rely on text coordination`;

  const outrageNote = provenance.outrage_compressed
    ? `Outrage compressed (max ${provenance.outrage_max?.toFixed(3) ?? "?"} under lexicon floor)`
    : `Outrage max ${provenance.outrage_max?.toFixed(3) ?? "n/a"} · mean ${provenance.outrage_mean?.toFixed(3) ?? "n/a"}`;

  const themeNote = provenance.theme_model_reliable
    ? `Themes: ${escapeHtml(provenance.theme_model)} · ${provenance.distinct_theme_count ?? "?"} distinct of ${provenance.theme_cluster_count ?? "?"} clusters`
    : `Themes: ${escapeHtml(provenance.theme_model)} (lexical fallback) · ${provenance.distinct_theme_count ?? "?"} distinct labels via c-TF-IDF`;

  return `<section class="panel panel-provenance" id="analysis-provenance-panel">
    <h2>Analysis scope</h2>
    <p class="chart-caption">
      Snapshot cohort${escapeHtml(truncated)} · sentiment aligned to same posts ·
      text coordination scanned across all ${provenance.posts_total_db} DB posts.
    </p>
    <dl class="provenance-grid">
      <div><dt>Text coordination</dt><dd><strong>${textScore.toFixed(2)}</strong></dd></div>
      <div><dt>Graph coordination</dt><dd><strong>${graphScore.toFixed(2)}</strong>${graphSufficient ? "" : " <span class='provenance-warn'>(sparse graph)</span>"}</dd></div>
      <div><dt>Combined index</dt><dd><strong>${cib.suspicion_score.toFixed(2)}</strong> · organic ${cib.organic_score.toFixed(2)}</dd></div>
      <div><dt>Outrage model</dt><dd>${escapeHtml(provenance.outrage_model_version)} · ${escapeHtml(outrageNote)}</dd></div>
      <div><dt>Propagation graph</dt><dd>${escapeHtml(graphNote)}</dd></div>
      <div><dt>Text signals</dt><dd>${provenance.duplicate_cluster_count} exact dup · ${provenance.fuzzy_cluster_count} fuzzy cross-author</dd></div>
      <div class="provenance-wide"><dt>Theme pipeline</dt><dd>${themeNote}</dd></div>
    </dl>
  </section>`;
}

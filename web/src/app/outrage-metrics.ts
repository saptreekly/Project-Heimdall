import { metricCardHtml, metricsGridHtml as metricsGridShell } from "../ui";
import { escapeHtml } from "../post-display";
import type { CibReport, NarrativeProvenance, Post } from "../types";

export function mean(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

export function outrageHistogram(posts: Post[]): Map<string, number> {
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

export function renderHistogram(posts: Post[]): string {
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

export function buildMetricsGrid(
  posts: Post[],
  authors: Set<string>,
  avg: number | null,
  cib: CibReport,
  provenance?: NarrativeProvenance | null
): string {
  const postsPerAuthor =
    provenance?.posts_per_author ??
    (authors.size > 0 ? Math.round((posts.length / authors.size) * 10) / 10 : null);
  const scoredCount = provenance?.outrage_scored_count ?? posts.filter((p) => p.outrage_index != null).length;
  const scoredPct =
    posts.length > 0 ? `${Math.round((scoredCount / posts.length) * 100)}% scored` : "";
  const outrageLabel = provenance?.outrage_compressed
    ? `max ${provenance.outrage_max?.toFixed(3) ?? "n/a"}`
    : avg != null
      ? `mean ${avg.toFixed(3)}`
      : "n/a";
  const outrageSub = provenance?.outrage_compressed
    ? `${scoredPct} · lexicon floor`
    : scoredPct;
  const postsLabel = provenance?.posts_truncated
    ? `${posts.length} / ${provenance.posts_total_db}`
    : `${posts.length}`;
  const fuzzyCount = provenance?.fuzzy_cluster_count ?? 0;
  const dupCount = provenance?.duplicate_cluster_count ?? 0;
  const graphNote = cib.graph_sufficient
    ? `graph ${cib.graph_suspicion_score.toFixed(2)} · ${cib.edge_count} edges`
    : `${fuzzyCount} fuzzy · ${dupCount} dup clusters`;

  return metricsGridShell(
    [
      metricCardHtml("Posts in view", postsLabel, postsPerAuthor != null ? `${postsPerAuthor} per author` : undefined),
      metricCardHtml("Unique authors", authors.size, `${posts.length} posts total`),
      metricCardHtml("Outrage", outrageLabel, outrageSub),
      metricCardHtml(
        "Text coordination",
        cib.text_coordination_score.toFixed(2),
        graphNote,
        true
      ),
    ].join("")
  );
}

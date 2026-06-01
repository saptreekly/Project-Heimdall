import { selectDuplicateCluster } from "./investigation";
import { escapeHtml, truncate } from "./post-display";
import type { CrossAuthorFuzzyCluster, NearDuplicatesReport } from "./types";

export function fuzzyAmplificationPanelHtml(report: NearDuplicatesReport | null): string {
  const th = report?.threshold ?? 0.82;
  const count = report?.cross_author_fuzzy_count ?? 0;
  const badge =
    count > 0
      ? `<span class="topology-badge topology-star">${count} fuzzy clusters</span>`
      : `<span class="topology-badge topology-sparse" id="fuzzy-threshold-badge">Jaccard ≥ ${th.toFixed(2)}</span>`;

  return `
    <section class="panel panel-fuzzy" id="fuzzy-amplification-panel">
      <h2>Cross-author fuzzy amplification ${badge}</h2>
      <p class="chart-caption">
        Token Jaccard similarity across <em>different</em> accounts (not exact-string match).
        Use the toolbar <strong>Jaccard threshold</strong> slider to widen or tighten lexical distance (live, no re-export).
        Click a cluster to filter posts.
      </p>
      <div id="fuzzy-clusters-host"></div>
    </section>
  `;
}

export function updateFuzzyThresholdBadge(threshold: number, clusterCount: number): void {
  const badge = document.querySelector("#fuzzy-amplification-panel .topology-badge");
  if (!badge) return;
  badge.textContent =
    clusterCount > 0
      ? `${clusterCount} fuzzy @ ${threshold.toFixed(2)}`
      : `Jaccard ≥ ${threshold.toFixed(2)}`;
  badge.classList.toggle("topology-star", clusterCount > 0);
  badge.classList.toggle("topology-sparse", clusterCount === 0);
}

export function renderFuzzyClusters(
  host: HTMLElement,
  report: NearDuplicatesReport | null
): void {
  const clusters = report?.cross_author_fuzzy ?? [];
  if (!clusters.length) {
    host.innerHTML =
      "<p class='loading'>No cross-author fuzzy clusters (need ≥2 posts from ≥2 authors with Jaccard ≥ threshold).</p>";
    return;
  }

  host.innerHTML = clusters
    .slice(0, 10)
    .map((c) => renderFuzzyClusterButton(c))
    .join("");

  host.querySelectorAll<HTMLButtonElement>(".fuzzy-cluster-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ids = (btn.dataset.postIds ?? "")
        .split(",")
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isFinite(n));
      const burst = btn.dataset.burst === "1";
      const sample = btn.querySelector(".post-text")?.textContent ?? "fuzzy cluster";
      selectDuplicateCluster(`Fuzzy: ${sample.slice(0, 36)}`, ids, burst);
      document.getElementById("posts-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function renderFuzzyClusterButton(c: CrossAuthorFuzzyCluster): string {
  const burst = c.burst_synchronized
    ? `<span class="burst-tag">${c.burst_author_count ?? c.author_count} authors in 90s burst</span>`
    : "";
  const timing =
    c.min_inter_arrival_seconds != null
      ? ` · min gap ${c.min_inter_arrival_seconds}s · span ${c.cluster_span_seconds ?? "?"}s`
      : "";
  const sim = (c.max_similarity * 100).toFixed(0);
  const ids = c.post_ids.join(",");
  return `<button type="button" class="cluster cluster-btn fuzzy-cluster-btn${c.burst_synchronized ? " cluster-burst" : ""}" data-post-ids="${ids}" data-burst="${c.burst_synchronized ? "1" : "0"}">
    <strong>${c.count} posts</strong> · ${c.author_count} authors · Jaccard ~${sim}%${burst}
    <p class="post-text">${escapeHtml(truncate(c.sample_text, 200))}</p>
    <p class="post-meta">authors: ${escapeHtml(c.author_ids.slice(0, 6).join(", "))}${c.author_ids.length > 6 ? "…" : ""}${timing}</p>
  </button>`;
}

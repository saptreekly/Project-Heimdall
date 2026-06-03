import {
  classifyDuplicateCluster,
  coordinationSummaryLine,
  type CoordinationTier,
} from "./cluster-coordination";
import { escapeHtml, truncate } from "./post-display";
import type {
  CoordinationOverlay,
  CoordinationSubclusterRef,
  CrossAuthorFuzzyCluster,
  DuplicateCluster,
  Post,
} from "./types";

const TIER_CLASS: Record<CoordinationTier, string> = {
  high: "coord-tier-high",
  medium: "coord-tier-medium",
  low: "coord-tier-low",
  context: "coord-tier-context",
};

function tierBadge(tier: CoordinationTier, label: string): string {
  return `<span class="coord-tier-badge ${TIER_CLASS[tier]}">${escapeHtml(label)}</span>`;
}

function renderSubclusterList(
  title: string,
  refs: CoordinationSubclusterRef[],
  emptyHint: string
): string {
  if (!refs.length) {
    return `<p class="inspector-coord-empty">${escapeHtml(emptyHint)}</p>`;
  }
  return `<ul class="inspector-subcluster-list">${refs
    .slice(0, 4)
    .map(
      (ref) => `<li class="inspector-subcluster">
        <div class="inspector-subcluster-head">
          <strong>${ref.overlap_count} overlapping posts</strong>
          <span class="inspector-subcluster-meta">${ref.author_count} authors · cluster size ${ref.cluster_count}${
            ref.burst_synchronized ? " · burst" : ""
          }</span>
        </div>
        <p class="inspector-subcluster-sample">${escapeHtml(truncate(ref.sample_text, 120))}</p>
      </li>`
    )
    .join("")}</ul>`;
}

export function renderCombinedClusterInspector(
  title: string,
  labels: string[],
  sampleText: string,
  posts: Post[],
  postIds: number[],
  overlay: CoordinationOverlay,
  options?: { resightings?: number }
): string {
  const tags = labels
    .map((label) => {
      const cls = label.includes(" ") ? "theme-token theme-token-phrase" : "theme-token";
      return `<span class="${cls}">${escapeHtml(label)}</span>`;
    })
    .join("");

  const tierBars = ["inflammatory", "escalating", "neutral", "unknown"]
    .map((tier) => {
      const count = posts.filter(
        (p) => postIds.includes(p.id) && (p.escalation_tier ?? "unknown") === tier
      ).length;
      return { tier, count };
    })
    .filter((row) => row.count > 0);
  const maxTier = Math.max(...tierBars.map((t) => t.count), 1);

  return `
    <div class="inspector-combined-card theme-detail">
      <div class="theme-detail-header">
        <h3>${escapeHtml(title)}</h3>
        <p class="theme-detail-meta">${tierBadge(overlay.tier, overlay.tier_label)}</p>
      </div>
      <dl class="inspector-stats inspector-coord-stats">
        <div><dt>Unique posts</dt><dd>${overlay.unique_post_count}</dd></div>
        <div><dt>Author spread</dt><dd>${overlay.unique_author_count} accounts</dd></div>
        <div><dt>Exact dup subclusters</dt><dd>${overlay.exact_duplicate_clusters.length}</dd></div>
        <div><dt>Fuzzy subclusters</dt><dd>${overlay.fuzzy_clusters.length}</dd></div>
        ${
          options?.resightings
            ? `<div><dt>Re-sightings (ingest)</dt><dd>${options.resightings}</dd></div>`
            : ""
        }
      </dl>
      <p class="inspector-coord-summary">${escapeHtml(coordinationSummaryLine(overlay))}</p>
      <div class="theme-detail-tags">${tags || "<span class='theme-token theme-token-empty'>(no labels)</span>"}</div>
      ${
        sampleText
          ? `<blockquote class="theme-detail-sample">${escapeHtml(truncate(sampleText, 320))}</blockquote>`
          : ""
      }
      ${
        tierBars.length
          ? `<div class="theme-tier-breakdown">${tierBars
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
      <section class="inspector-coord-section">
        <h4>Copy coordination</h4>
        ${renderSubclusterList(
          "Exact duplicates",
          overlay.exact_duplicate_clusters,
          "No exact duplicate subclusters overlap this frame."
        )}
      </section>
      <section class="inspector-coord-section">
        <h4>Frame coordination</h4>
        ${renderSubclusterList(
          "Fuzzy clusters",
          overlay.fuzzy_clusters,
          "No cross-author fuzzy subclusters overlap this frame — wording may be fully paraphrased."
        )}
      </section>
      <button type="button" class="btn btn-secondary btn-small theme-detail-cta" id="inspector-view-theme-posts">
        View ${overlay.unique_post_count} posts →
      </button>
    </div>
  `;
}

export function renderDuplicateClusterInspector(
  cluster: DuplicateCluster | CrossAuthorFuzzyCluster,
  kind: "exact" | "fuzzy",
  parentThemeLabel: string | null
): string {
  const classified = classifyDuplicateCluster(cluster, kind);
  const kindLabel = kind === "exact" ? "Exact duplicate cluster" : "Cross-author fuzzy cluster";
  return `
    <div class="inspector-combined-card">
      <div class="theme-detail-header">
        <h3>${escapeHtml(kindLabel)}</h3>
        <p class="theme-detail-meta">${tierBadge(classified.tier, classified.label)}</p>
      </div>
      <dl class="inspector-stats inspector-coord-stats">
        <div><dt>Posts</dt><dd>${cluster.count}</dd></div>
        <div><dt>Authors</dt><dd>${cluster.author_count ?? cluster.author_ids.length}</dd></div>
        ${
          cluster.burst_synchronized
            ? `<div><dt>Burst</dt><dd>${cluster.burst_author_count ?? cluster.author_count} authors synchronized</dd></div>`
            : ""
        }
        ${
          parentThemeLabel
            ? `<div><dt>Related frame</dt><dd>${escapeHtml(parentThemeLabel)}</dd></div>`
            : ""
        }
      </dl>
      <blockquote class="theme-detail-sample">${escapeHtml(truncate(cluster.sample_text, 320))}</blockquote>
      <p class="inspector-coord-empty">Layer 1 signal — same or near-same text across accounts. Compare with <strong>Frames</strong> for paraphrased narrative alignment.</p>
      <button type="button" class="btn btn-secondary btn-small theme-detail-cta" id="inspector-view-cluster-posts">
        View ${cluster.count} posts →
      </button>
    </div>
  `;
}

export function bindInspectorViewTheme(onView: () => void): void {
  document.getElementById("inspector-view-theme-posts")?.addEventListener("click", onView);
}

export function bindInspectorViewCluster(onView: () => void): void {
  document.getElementById("inspector-view-cluster-posts")?.addEventListener("click", onView);
}

export function resetInspectorEmpty(): void {
  const body = document.getElementById("desk-inspector-body");
  const sub = document.getElementById("desk-inspector-sub");
  if (sub) sub.textContent = "Select a frame, author, or cluster";
  if (body) {
    body.innerHTML =
      '<p class="desk-inspector-empty">Nothing selected yet. Pick a theme in <strong>Frames</strong>, a duplicate cluster in <strong>Network</strong>, or follow an alert from <strong>Pulse</strong>.</p>';
  }
}

export function setInspectorContext(title: string, html: string): void {
  const body = document.getElementById("desk-inspector-body");
  const sub = document.getElementById("desk-inspector-sub");
  if (sub) sub.textContent = title;
  if (body) body.innerHTML = html;
}

export function renderAuthorInspector(
  authorId: string,
  label: string,
  posts: Post[],
  edgeCount?: number
): string {
  const authorPosts = posts.filter((p) => p.author_id === authorId);
  const avgOutrage =
    authorPosts.filter((p) => p.outrage_index != null).length > 0
      ? (
          authorPosts.reduce((sum, p) => sum + (p.outrage_index ?? 0), 0) /
          authorPosts.filter((p) => p.outrage_index != null).length
        ).toFixed(3)
      : "n/a";
  const sample = authorPosts
    .slice()
    .sort((a, b) => (b.outrage_index ?? 0) - (a.outrage_index ?? 0))[0];

  return `
    <div class="inspector-card">
      <h3>${escapeHtml(label)}</h3>
      <p class="inspector-meta">${authorPosts.length} post${authorPosts.length === 1 ? "" : "s"} in narrative${edgeCount != null ? ` · graph context ${edgeCount} edges` : ""}</p>
      <dl class="inspector-stats">
        <div><dt>Author ID</dt><dd><code>${escapeHtml(authorId.slice(0, 24))}${authorId.length > 24 ? "…" : ""}</code></dd></div>
        <div><dt>Mean outrage</dt><dd>${avgOutrage}</dd></div>
      </dl>
      ${
        sample
          ? `<blockquote class="inspector-sample">${escapeHtml(sample.text.slice(0, 280))}${sample.text.length > 280 ? "…" : ""}</blockquote>`
          : ""
      }
      <button type="button" class="btn btn-secondary btn-small" id="inspector-view-author-posts">View posts →</button>
    </div>
  `;
}

export function bindInspectorViewAuthor(onView: () => void): void {
  document.getElementById("inspector-view-author-posts")?.addEventListener("click", onView);
}

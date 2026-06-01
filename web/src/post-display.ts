import type { AuthorSpamSummary, NearDuplicatesReport, Post } from "./types";
import { selectAuthor } from "./investigation";
import { stateEmptyHtml } from "./ui-states";

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function truncate(s: string, n: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= n ? t : `${t.slice(0, n)}…`;
}

const SENSITIVE_RE =
  /\b(nazi|fascist|facist|pig|kill|inbreed|pathetic)\b/i;

export function isSensitiveText(text: string): boolean {
  return SENSITIVE_RE.test(text);
}

export function postStatusLink(p: Post): string {
  if (p.status_url) return p.status_url;
  if (p.platform === "x" && p.external_id) {
    return `https://x.com/i/web/status/${p.external_id}`;
  }
  return "";
}

function authorLabelPlain(p: Post): string {
  return p.author_handle ?? `author ${p.author_id.slice(0, 10)}…`;
}

function authorLabel(p: Post): string {
  return escapeHtml(authorLabelPlain(p));
}

function renderPostItem(p: Post, activeAuthorId: string | null, blurSensitive: boolean): string {
  const link = postStatusLink(p);
  const tweetMeta = p.external_id
    ? `<span class="post-tweet-id" title="Tweet ID">tweet ${escapeHtml(p.external_id.slice(0, 14))}…</span>`
    : "";
  const nearTag =
    p.near_duplicate_group != null
      ? `<span class="tag tag-near-dup">same-author #${p.near_duplicate_group}</span>`
      : "";
  const fuzzyTag =
    p.cross_author_fuzzy_cluster != null
      ? `<span class="tag tag-fuzzy-cross">fuzzy ×${p.cross_author_fuzzy_cluster}</span>`
      : "";
  const pastaTag =
    p.copypasta_score != null && p.copypasta_score >= 0.75
      ? `<span class="tag tag-copypasta">copypasta ${(p.copypasta_score * 100).toFixed(0)}%</span>`
      : "";
  const sensitive = blurSensitive && isSensitiveText(p.text);
  return `<li class="post-item${activeAuthorId === p.author_id ? " post-item-active" : ""}" data-author-id="${escapeHtml(p.author_id)}">
    <div class="post-meta">
      <span>${escapeHtml(p.platform)}</span>
      <button type="button" class="link-btn author-link" data-author-id="${escapeHtml(p.author_id)}" data-author-label="${escapeHtml(authorLabelPlain(p))}">${authorLabel(p)}</button>
      ${tweetMeta}
      <span>${escapeHtml(p.posted_at.slice(0, 16))}</span>
      ${nearTag}
      ${fuzzyTag}
      ${pastaTag}
      <span class="outrage-tag">outrage ${p.outrage_index?.toFixed(3) ?? "n/a"}</span>
    </div>
    <p class="post-text${sensitive ? " post-text-blurred" : ""}">${escapeHtml(truncate(p.text, 280))}</p>
    ${
      link
        ? `<p class="post-actions"><a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Open on X</a></p>`
        : ""
    }
  </li>`;
}

function groupByAuthor(posts: Post[]): Map<string, Post[]> {
  const map = new Map<string, Post[]>();
  for (const p of posts) {
    const list = map.get(p.author_id) ?? [];
    list.push(p);
    map.set(p.author_id, list);
  }
  return map;
}

function renderAuthorRollup(
  authorId: string,
  items: Post[],
  summary: AuthorSpamSummary | undefined,
  activeAuthorId: string | null,
  blurSensitive: boolean
): string {
  const label = items[0]?.author_handle ?? `author ${authorId.slice(0, 10)}…`;
  const nearNote =
    summary?.near_duplicate_count && summary.near_duplicate_count >= 2
      ? ` · ${summary.near_duplicate_count} near-identical`
      : "";
  const span =
    summary?.span_hours != null && summary.span_hours > 0
      ? ` · ${summary.span_hours}h span`
      : "";
  const inner = items
    .map((p) => renderPostItem(p, activeAuthorId, blurSensitive))
    .join("");
  return `<details class="author-rollup" open>
    <summary>
      <strong>${escapeHtml(label)}</strong>
      <span class="rollup-meta">${items.length} posts${nearNote}${span}</span>
    </summary>
    <ul class="post-list post-list-nested">${inner}</ul>
  </details>`;
}

export function renderPostsList(
  posts: Post[],
  options: {
    limit?: number;
    activeAuthorId?: string | null;
    blurSensitive?: boolean;
    nearDup?: NearDuplicatesReport | null;
    groupAuthors?: boolean;
  }
): string {
  const limit = options.limit ?? 50;
  const sorted = [...posts].sort(
    (a, b) => (b.outrage_index ?? -1) - (a.outrage_index ?? -1)
  );
  const top = sorted.slice(0, limit);
  if (top.length === 0) {
    return stateEmptyHtml(
      "No posts match the current filters",
      "Clear the investigation filter or widen the time window."
    );
  }

  const summaryByAuthor = new Map(
    (options.nearDup?.author_summaries ?? []).map((s) => [s.author_id, s])
  );
  const active = options.activeAuthorId ?? null;
  const blur = options.blurSensitive ?? false;

  if (!options.groupAuthors) {
    return `<ul class="post-list">${top
      .map((p) => renderPostItem(p, active, blur))
      .join("")}</ul>`;
  }

  const byAuthor = groupByAuthor(top);
  const multi = [...byAuthor.entries()].filter(([, items]) => items.length >= 3);
  const multiIds = new Set(multi.map(([id]) => id));
  const singles = top.filter((p) => !multiIds.has(p.author_id));

  const rollups = multi
    .map(([id, items]) =>
      renderAuthorRollup(id, items, summaryByAuthor.get(id), active, blur)
    )
    .join("");
  const singleList =
    singles.length > 0
      ? `<ul class="post-list">${singles
          .map((p) => renderPostItem(p, active, blur))
          .join("")}</ul>`
      : "";

  return `<div class="post-list-mixed">${rollups}${singleList}</div>`;
}

export function bindPostListAuthorLinks(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>(".author-link").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const id = btn.dataset.authorId;
      const label = btn.dataset.authorLabel?.replace(/<[^>]+>/g, "") ?? id;
      if (id) selectAuthor(id, label ?? id);
    });
  });
}

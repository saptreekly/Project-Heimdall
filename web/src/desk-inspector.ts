import { escapeHtml } from "./post-display";
import type { Post } from "./types";

export function resetInspectorEmpty(): void {
  const body = document.getElementById("desk-inspector-body");
  const sub = document.getElementById("desk-inspector-sub");
  if (sub) sub.textContent = "Select a frame, author, or cluster";
  if (body) {
    body.innerHTML =
      '<p class="desk-inspector-empty">Nothing selected yet. Pick a theme in <strong>Frames</strong>, an author in <strong>Network</strong>, or follow an alert from <strong>Pulse</strong>.</p>';
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

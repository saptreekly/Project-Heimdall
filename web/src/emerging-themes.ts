import { selectThemeCluster } from "./investigation";
import type { ThemesReport } from "./types";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatTermTokens(terms: string[]): string {
  if (terms.length === 0) return '<span class="theme-token theme-token-empty">(no terms)</span>';
  return terms
    .map((t) => `<span class="theme-token">${escapeHtml(t)}</span>`)
    .join("");
}

function cardLabel(terms: string[]): string {
  if (terms.length === 0) return "unnamed cluster";
  return terms.slice(0, 4).join(" · ");
}

export function emergingThemesPanelHtml(report: ThemesReport): string {
  const emerging = report.emerging_theme_count ?? 0;
  const badge =
    emerging > 0
      ? `<span class="topology-badge topology-star">${emerging} emerging</span>`
      : `<span class="topology-badge topology-sparse">embedding clusters</span>`;

  return `
    <section class="panel panel-chart-wide themes-panel" id="emerging-themes-panel">
      <h2>Emerging themes timeline ${badge}</h2>
      <p class="chart-caption">
        DBSCAN/KMeans on sentence embeddings surfaces coordinated phrasing variants beyond exact-string duplicates.
        Click a cluster to filter posts below.
      </p>
      <div id="themes-timeline-host" class="themes-timeline-host">
        <p class="loading">Loading themes…</p>
      </div>
      <p class="metric-sub themes-meta" id="themes-meta"></p>
    </section>
  `;
}

export function renderEmergingThemesTimeline(
  host: HTMLElement,
  report: ThemesReport
): void {
  const meta = document.getElementById("themes-meta");

  if (!report.available) {
    host.innerHTML = `<p class="empty">${escapeHtml(report.reason ?? "Theme clustering unavailable in this snapshot.")}</p>`;
    if (meta) meta.textContent = report.method ? `Method: ${report.method}` : "";
    return;
  }

  const timeline = report.timeline?.length
    ? report.timeline
    : report.clusters.map((c) => ({
        cluster_id: c.cluster_id,
        label_terms: c.label_terms,
        emerging_theme: c.emerging_theme,
        size: c.size,
        first_seen: null,
        last_seen: null,
        post_ids: c.post_ids,
      }));

  if (timeline.length === 0) {
    host.innerHTML =
      "<p class='empty'>No embedding clusters for this narrative (need ≥3 posts and USE_EMBEDDING_THEMES on export).</p>";
    if (meta) meta.textContent = `Model: ${report.model} · ${report.post_count} posts`;
    return;
  }

  host.innerHTML = `<div class="themes-timeline">${timeline
    .map((entry) => {
      const terms = entry.label_terms ?? [];
      const label = cardLabel(terms);
      const span =
        entry.first_seen && entry.last_seen
          ? entry.first_seen === entry.last_seen
            ? entry.first_seen
            : `${entry.first_seen} → ${entry.last_seen}`
          : "date unknown";
      return `<button
        type="button"
        class="theme-card${entry.emerging_theme ? " theme-card-emerging" : ""}"
        data-cluster-id="${entry.cluster_id}"
        data-post-ids="${(entry.post_ids ?? []).join(",")}"
        aria-label="Theme cluster ${escapeHtml(label)}"
      >
        <span class="theme-card-date">${escapeHtml(span)}</span>
        <span class="theme-card-tokens">${formatTermTokens(terms)}</span>
        <span class="theme-card-meta">${entry.size} posts · cohesion cluster #${entry.cluster_id}${
          entry.emerging_theme ? " · emerging" : ""
        }</span>
      </button>`;
    })
    .join("")}</div>`;

  host.querySelectorAll<HTMLButtonElement>(".theme-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ids = (btn.dataset.postIds ?? "")
        .split(",")
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isFinite(n));
      const clusterId = btn.dataset.clusterId ?? "?";
      const card = timeline.find((t) => String(t.cluster_id) === clusterId);
      const terms = card?.label_terms ?? [];
      const label = terms.length ? `[${terms.join(", ")}]` : `cluster ${clusterId}`;

      host.querySelectorAll(".theme-card").forEach((c) => c.classList.remove("theme-card-active"));
      btn.classList.add("theme-card-active");

      selectThemeCluster(label, ids);
      document.getElementById("posts-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  if (meta) {
    meta.textContent = `${report.cluster_count} clusters · ${report.emerging_theme_count} emerging · ${report.method} · ${report.model}`;
  }
}

export function clearThemeCardSelection(): void {
  document.querySelectorAll(".theme-card-active").forEach((el) => {
    el.classList.remove("theme-card-active");
  });
}

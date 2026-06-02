import { selectThemeCluster } from "./investigation";
import type { ThemesReport } from "./types";
import { stateLoadingHtml } from "./ui-states";

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
    ? `<p class="chart-caption provenance-warn">Lexical TF-IDF fallback — treat emerging labels as low confidence until neural embeddings are enabled on export.</p>`
    : "";
  const inner = `
      <h2 class="themes-panel-title">Emerging themes timeline ${badge}</h2>
      ${fallbackNote}
      <p class="chart-caption">
        Labels use c-TF-IDF — terms distinctive to each cluster vs the full narrative, with shared vocabulary deduplicated across themes.
        Click a cluster to filter posts below.
      </p>
      <div id="themes-timeline-host" class="themes-timeline-host">
        ${stateLoadingHtml("Loading themes…")}
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
  report: ThemesReport
): void {
  const meta = document.getElementById("themes-meta");

  if (!report.available) {
    const hint = report.reason?.includes("USE_EMBEDDING_THEMES")
      ? " Re-export with USE_EMBEDDING_THEMES=true (pip install -e \".[ml]\" on Python 3.11–3.12 for neural embeddings, or base install for TF-IDF fallback)."
      : "";
    host.innerHTML = `<p class="empty">${escapeHtml(report.reason ?? "Theme clustering unavailable in this snapshot.")}${escapeHtml(hint)}</p>`;
    if (meta) meta.textContent = report.method ? `Method: ${report.method}` : "";
    return;
  }

  const timeline = report.timeline?.length
    ? report.timeline
    : report.clusters
        .filter(
          (c) =>
            (c.label_distinctiveness ?? 0) >= 0.12 ||
            c.emerging_theme
        )
        .map((c) => ({
        cluster_id: c.cluster_id,
        label_terms: c.label_terms,
        label_distinctiveness: c.label_distinctiveness,
        emerging_theme: c.emerging_theme,
        size: c.size,
        first_seen: c.first_seen ?? null,
        last_seen: c.last_seen ?? null,
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
      const distinctPct =
        entry.label_distinctiveness != null
          ? Math.round(entry.label_distinctiveness * 100)
          : null;
      return `<button
        type="button"
        class="theme-card${entry.emerging_theme ? " theme-card-emerging" : ""}"
        data-cluster-id="${entry.cluster_id}"
        data-post-ids="${(entry.post_ids ?? []).join(",")}"
        aria-label="Theme cluster ${escapeHtml(label)}"
      >
        <span class="theme-card-date">${escapeHtml(span)}</span>
        <span class="theme-card-tokens">${formatTermTokens(terms)}</span>
        <span class="theme-card-meta">${entry.size} posts${
          distinctPct != null ? ` · ${distinctPct}% distinct` : ""
        }${entry.emerging_theme ? " · emerging" : ""}</span>
        <span class="cluster-cta">View ${entry.size} posts →</span>
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
      window.dispatchEvent(new CustomEvent("heimdall:goto-posts"));
    });
  });

  if (meta) {
    const encoder =
      report.model === "tfidf-fallback"
        ? "TF-IDF lexical vectors"
        : report.model;
    meta.textContent = `${report.distinct_theme_count ?? report.cluster_count} distinct · ${report.emerging_theme_count} emerging · ${report.method} · ${encoder}`;
  }
}

export function clearThemeCardSelection(): void {
  document.querySelectorAll(".theme-card-active").forEach((el) => {
    el.classList.remove("theme-card-active");
  });
}

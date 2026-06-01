import {
  clearSnapshotCache,
  DATA_LINKS,
  fetchAmplification,
  fetchCib,
  fetchPosts,
  fetchSentimentShift,
  getSnapshotGeneratedAt,
  listNarratives,
  loadSnapshot,
} from "./api";
import type { DuplicateCluster, NarrativeSummary, Post } from "./types";

const rootEl = document.getElementById("app");
if (!rootEl) throw new Error("#app missing");
const root: HTMLElement = rootEl;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truncate(s: string, n: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= n ? t : `${t.slice(0, n)}…`;
}

function mean(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function outrageHistogram(posts: Post[]): Map<string, number> {
  const bins = new Map<string, number>([
    ["0–0.2", 0],
    ["0.2–0.4", 0],
    ["0.4–0.6", 0],
    ["0.6–0.8", 0],
    ["0.8–1.0", 0],
    ["(none)", 0],
  ]);
  for (const p of posts) {
    const o = p.outrage_index;
    if (o == null) {
      bins.set("(none)", (bins.get("(none)") ?? 0) + 1);
      continue;
    }
    if (o < 0.2) bins.set("0–0.2", (bins.get("0–0.2") ?? 0) + 1);
    else if (o < 0.4) bins.set("0.2–0.4", (bins.get("0.2–0.4") ?? 0) + 1);
    else if (o < 0.6) bins.set("0.4–0.6", (bins.get("0.4–0.6") ?? 0) + 1);
    else if (o < 0.8) bins.set("0.6–0.8", (bins.get("0.6–0.8") ?? 0) + 1);
    else bins.set("0.8–1.0", (bins.get("0.8–1.0") ?? 0) + 1);
  }
  return bins;
}

function renderHistogram(posts: Post[]): string {
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

function renderPosts(posts: Post[], limit = 12): string {
  const sorted = [...posts].sort(
    (a, b) => (b.outrage_index ?? -1) - (a.outrage_index ?? -1)
  );
  const top = sorted.slice(0, limit);
  if (top.length === 0) return "<p class='loading'>No posts in this narrative.</p>";
  return `<ul class="post-list">${top
    .map(
      (p) => `<li class="post-item">
        <div class="post-meta">
          <span>${escapeHtml(p.platform)}</span>
          <span>${escapeHtml(p.author_id)}</span>
          <span>${escapeHtml(p.posted_at.slice(0, 16))}</span>
          <span class="outrage-tag">outrage ${p.outrage_index?.toFixed(3) ?? "—"}</span>
        </div>
        <p class="post-text">${escapeHtml(truncate(p.text, 280))}</p>
      </li>`
    )
    .join("")}</ul>`;
}

function renderClusters(clusters: DuplicateCluster[]): string {
  if (clusters.length === 0) {
    return "<p class='loading'>No duplicate-text clusters (need ≥2 posts with identical normalized text).</p>";
  }
  return clusters
    .slice(0, 8)
    .map(
      (c) => `<div class="cluster">
        <strong>${c.count} posts</strong> · ${c.author_count} authors
        <p class="post-text">${escapeHtml(truncate(c.sample_text, 200))}</p>
        <p class="post-meta">authors: ${escapeHtml(c.author_ids.slice(0, 5).join(", "))}${c.author_ids.length > 5 ? "…" : ""}</p>
      </div>`
    )
    .join("");
}

function renderSentimentChart(
  buckets: Array<{ date: string; mean_outrage: number; count: number }>
): string {
  if (buckets.length === 0) {
    return "<p class='loading'>Not enough dated posts for a timeline.</p>";
  }
  const max = Math.max(...buckets.map((b) => b.mean_outrage), 0.01);
  const rows = buckets
    .map((b) => {
      const pct = (b.mean_outrage / max) * 100;
      return `<div class="bar-row">
        <span class="bar-label">${escapeHtml(b.date)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <span>${b.mean_outrage.toFixed(2)} (${b.count})</span>
      </div>`;
    })
    .join("");
  return `<div class="chart">${rows}</div>`;
}

function shell(narratives: NarrativeSummary[], selectedId: number, generatedAt: string | null): string {
  const options = narratives
    .map(
      (n) =>
        `<option value="${n.id}" ${n.id === selectedId ? "selected" : ""}>${escapeHtml(n.name)} (${n.post_count} posts)</option>`
    )
    .join("");
  const stamp = generatedAt ? ` · ${escapeHtml(generatedAt.slice(0, 19))} UTC` : "";
  return `
    <header>
      <h1>Heimdall — Narrative Analysis</h1>
      <p class="data-badge">Repo snapshot${stamp}</p>
      <p class="data-links">
        Source data:
        <a href="${DATA_LINKS.snapshot}" target="_blank" rel="noopener">snapshot.json</a>
        ·
        <a href="${DATA_LINKS.database}" target="_blank" rel="noopener">heimdall.db</a>
        ·
        <a href="${DATA_LINKS.publishDocs}" target="_blank" rel="noopener">how to update</a>
      </p>
    </header>
    <div class="toolbar">
      <label for="narrative-select">Narrative</label>
      <select id="narrative-select">${options}</select>
      <button type="button" id="refresh-btn">Refresh</button>
    </div>
    <main id="content"><p class="loading">Loading…</p></main>
  `;
}

function renderMissingSnapshot(message: string): void {
  root.innerHTML = `
    <header><h1>Heimdall — Narrative Analysis</h1></header>
    <main>
      <div class="error">
        <strong>No snapshot data</strong>
        <p>${escapeHtml(message)}</p>
        <p class="sub">Publish ingest to the repo with <code>python scripts/publish_dashboard_data.py</code>, then redeploy Pages.</p>
        <p class="data-links">
          <a href="${DATA_LINKS.publishDocs}" target="_blank" rel="noopener">data/dashboard/README.md</a>
        </p>
      </div>
    </main>
  `;
}

async function loadDashboard(narrativeId: number): Promise<void> {
  const content = document.getElementById("content");
  if (!content) return;
  content.innerHTML = "<p class='loading'>Loading…</p>";

  try {
    const [posts, cib, sentiment, amp] = await Promise.all([
      fetchPosts(narrativeId),
      fetchCib(narrativeId),
      fetchSentimentShift(narrativeId),
      fetchAmplification(narrativeId),
    ]);

    const scored = posts.filter((p) => p.outrage_index != null);
    const outrageVals = scored.map((p) => p.outrage_index as number);
    const authors = new Set(posts.map((p) => p.author_id));
    const avg = mean(outrageVals);

    content.innerHTML = `
      <div class="grid">
        <div class="card"><h2>Posts</h2><div class="value">${posts.length}</div></div>
        <div class="card"><h2>Authors</h2><div class="value">${authors.size}</div></div>
        <div class="card"><h2>Mean outrage</h2><div class="value">${avg != null ? avg.toFixed(3) : "—"}</div></div>
        <div class="card"><h2>CIB suspicion</h2><div class="value">${cib.suspicion_score.toFixed(2)}</div>
          <div class="sub">organic ${cib.organic_score.toFixed(2)} · ${cib.edge_count} edges</div></div>
      </div>

      <section>
        <h2>Outrage distribution</h2>
        ${renderHistogram(posts)}
      </section>

      <section>
        <h2>Sentiment shift (${escapeHtml(sentiment.trend)})</h2>
        ${renderSentimentChart(sentiment.buckets)}
      </section>

      <section>
        <h2>Duplicate text (amplification)</h2>
        ${renderClusters(amp.clusters)}
      </section>

      <section>
        <h2>CIB signals</h2>
        <div class="card">
          ${cib.signals.length ? `<ul>${cib.signals.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : "<p class='loading'>No elevated CIB signals.</p>"}
          ${
            cib.iu_astroturf
              ? `<p class="sub">IU astroturf: ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors</p>`
              : ""
          }
        </div>
      </section>

      <section>
        <h2>Top posts by outrage</h2>
        ${renderPosts(posts)}
      </section>
    `;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    content.innerHTML = `<div class="error"><strong>Failed to load narrative ${narrativeId}</strong><p>${escapeHtml(msg)}</p></div>`;
  }
}

function narrativeIdFromUrl(): number | null {
  const p = new URLSearchParams(window.location.search);
  const n = p.get("narrative");
  if (!n) return null;
  const id = parseInt(n, 10);
  return Number.isFinite(id) ? id : null;
}

function setUrlNarrative(id: number): void {
  const url = new URL(window.location.href);
  url.searchParams.set("narrative", String(id));
  window.history.replaceState({}, "", url);
}

function bindDashboardControls(narratives: NarrativeSummary[], initialId: number): void {
  let selected = initialId;
  const select = document.getElementById("narrative-select") as HTMLSelectElement;
  const refresh = document.getElementById("refresh-btn");

  const run = () => {
    selected = parseInt(select.value, 10);
    setUrlNarrative(selected);
    void loadDashboard(selected);
  };

  select.addEventListener("change", run);
  refresh?.addEventListener("click", () => {
    clearSnapshotCache();
    void bootstrap();
  });
  run();
}

async function bootstrap(): Promise<void> {
  try {
    await loadSnapshot();
    const narratives = await listNarratives();
    if (narratives.length === 0) {
      renderMissingSnapshot("Snapshot has no narratives.");
      return;
    }

    const selected =
      narrativeIdFromUrl() ??
      narratives.find((n) => n.name === "midterms_2026")?.id ??
      narratives[0].id;

    root.innerHTML = shell(narratives, selected, getSnapshotGeneratedAt());
    bindDashboardControls(narratives, selected);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    renderMissingSnapshot(msg);
  }
}

void bootstrap();

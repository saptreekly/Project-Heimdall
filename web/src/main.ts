import {
  DEFAULT_API_BASE,
  fetchAmplification,
  fetchCib,
  fetchPosts,
  fetchSentimentShift,
  getApiBase,
  getSnapshotGeneratedAt,
  isStaticMode,
  listNarratives,
  clearSnapshotCache,
  loadSnapshot,
  setApiBase,
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

function shell(
  narratives: NarrativeSummary[],
  selectedId: number,
  opts: { staticData: boolean; generatedAt: string | null }
): string {
  const options = narratives
    .map(
      (n) =>
        `<option value="${n.id}" ${n.id === selectedId ? "selected" : ""}>${escapeHtml(n.name)} (${n.post_count} posts)</option>`
    )
    .join("");
  const dataNote = opts.staticData
    ? `<p class="data-badge">Bundled snapshot${opts.generatedAt ? ` · ${escapeHtml(opts.generatedAt.slice(0, 19))} UTC` : ""}</p>`
    : `<p>Live data from your Heimdall API (or export a snapshot for GitHub Pages).</p>`;
  const apiRow = opts.staticData
    ? `<details class="api-fallback"><summary>Live API (optional)</summary>
      <div class="toolbar-inner">
        <label for="api-base">API base</label>
        <input id="api-base" type="url" class="api-input" value="${escapeHtml(getApiBase())}" placeholder="${escapeHtml(DEFAULT_API_BASE)}" />
        <button type="button" id="api-connect-btn">Use live API</button>
      </div></details>`
    : `<div class="toolbar-row">
      <label for="api-base">API base</label>
      <input id="api-base" type="url" class="api-input" value="${escapeHtml(getApiBase())}" placeholder="${escapeHtml(DEFAULT_API_BASE)}" />
      <button type="button" id="api-connect-btn">Connect</button>
    </div>`;
  return `
    <header>
      <h1>Heimdall — Narrative Analysis</h1>
      ${dataNote}
    </header>
    <div class="toolbar">
      ${apiRow}
      <div class="toolbar-row">
        <label for="narrative-select">Narrative</label>
        <select id="narrative-select">${options}</select>
        <button type="button" id="refresh-btn">Refresh</button>
      </div>
    </div>
    <main id="content"><p class="loading">Loading…</p></main>
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
    content.innerHTML = `<div class="error"><strong>Failed to load narrative ${narrativeId}</strong><p>${escapeHtml(msg)}</p><p class="sub">Run <code>uvicorn heimdall.main:app --reload</code>, set API base above (CORS must allow this origin), then Connect.</p></div>`;
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

function readApiBaseFromToolbar(): void {
  const input = document.getElementById("api-base") as HTMLInputElement | null;
  if (input?.value.trim()) setApiBase(input.value);
}

function bindDashboardControls(
  narratives: NarrativeSummary[],
  initialId: number
): void {
  let selected = initialId;
  const select = document.getElementById("narrative-select") as HTMLSelectElement;
  const refresh = document.getElementById("refresh-btn");
  const connect = document.getElementById("api-connect-btn");

  const run = () => {
    selected = parseInt(select.value, 10);
    setUrlNarrative(selected);
    void loadDashboard(selected);
  };

  select.addEventListener("change", run);
  refresh?.addEventListener("click", run);
  connect?.addEventListener("click", () => {
    readApiBaseFromToolbar();
    clearSnapshotCache();
    void bootstrap();
  });
  run();
}

async function bootstrap(): Promise<void> {
  const content = document.getElementById("content");
  if (content) content.innerHTML = "<p class='loading'>Loading…</p>";

  try {
    readApiBaseFromToolbar();
    const narratives = await listNarratives();
    if (narratives.length === 0) {
      if (content) {
        content.innerHTML =
          "<p class='error'>No narratives in database. Run an ingest against this API first.</p>";
      }
      return;
    }

    const selected =
      narrativeIdFromUrl() ??
      narratives.find((n) => n.name === "midterms_2026")?.id ??
      narratives[0].id;

    root.innerHTML = shell(narratives, selected, {
      staticData: isStaticMode(),
      generatedAt: getSnapshotGeneratedAt(),
    });
    bindDashboardControls(narratives, selected);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (content) {
      content.innerHTML = `<div class="error"><strong>Cannot reach API</strong><p>${escapeHtml(msg)}</p><p class="sub">API: <code>${escapeHtml(getApiBase())}</code></p></div>`;
    } else {
      root.innerHTML = `<div class="error"><strong>Cannot reach API</strong><p>${escapeHtml(msg)}</p></div>`;
    }
  }
}

async function init(): Promise<void> {
  const snap = await loadSnapshot();
  if (snap?.narratives.length) {
    await bootstrap();
    return;
  }

  root.innerHTML = shell([], 0, { staticData: false, generatedAt: null });
  const select = document.getElementById("narrative-select") as HTMLSelectElement;
  select.innerHTML = "<option value=''>Connect to load narratives</option>";
  select.disabled = true;
  document.getElementById("refresh-btn")?.setAttribute("disabled", "true");
  document.getElementById("api-connect-btn")?.addEventListener("click", () => void bootstrap());
}

void init();

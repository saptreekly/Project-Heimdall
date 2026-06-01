import { selectAuthor } from "./investigation";
import { escapeHtml } from "./post-display";
import type {
  CrossPollinationActor,
  CrossPollinationNarrativeRef,
  CrossPollinationReport,
  NarrativePollinationHits,
  NarrativePairOverlap,
} from "./types";

/** Distinct hues for narrative silos — stable by narrative_id. */
const NARRATIVE_PALETTE = [
  { bg: "#2980b9", fg: "#ecf6ff", border: "#5dade2" },
  { bg: "#c0392b", fg: "#fff0ee", border: "#e74c3c" },
  { bg: "#27ae60", fg: "#eafff3", border: "#58d68d" },
  { bg: "#8e44ad", fg: "#f9eeff", border: "#bb8fce" },
  { bg: "#d68910", fg: "#fff8e8", border: "#f4d03f" },
  { bg: "#16a085", fg: "#e8fff9", border: "#48c9b0" },
  { bg: "#c2185b", fg: "#ffeef4", border: "#f06292" },
  { bg: "#5c6bc0", fg: "#eef0ff", border: "#9fa8da" },
];

function narrativePaletteIndex(narrativeId: number): number {
  return Math.abs(narrativeId) % NARRATIVE_PALETTE.length;
}

function shortenNarrativeName(name: string, max = 18): string {
  const t = name.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function collectNarrativesFromReport(report: CrossPollinationReport | null): CrossPollinationNarrativeRef[] {
  const byId = new Map<number, CrossPollinationNarrativeRef>();
  for (const actor of report?.actors ?? []) {
    for (const n of actor.narratives) {
      if (!byId.has(n.narrative_id)) byId.set(n.narrative_id, n);
    }
  }
  return [...byId.values()].sort((a, b) => a.narrative_name.localeCompare(b.narrative_name));
}

function renderNarrativePill(
  ref: CrossPollinationNarrativeRef,
  options?: { current?: boolean; also?: boolean }
): string {
  const idx = narrativePaletteIndex(ref.narrative_id);
  const short = shortenNarrativeName(ref.narrative_name);
  const title = `${ref.narrative_name} · ${ref.post_count} post(s)`;
  const flags = [
    options?.current ? "cross-narr-pill-current" : "",
    options?.also ? "cross-narr-pill-also" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `<span
    class="cross-narr-pill cross-narr-pill-${idx}${flags ? ` ${flags}` : ""}"
    style="--pill-bg:${NARRATIVE_PALETTE[idx]!.bg};--pill-fg:${NARRATIVE_PALETTE[idx]!.fg};--pill-border:${NARRATIVE_PALETTE[idx]!.border}"
    title="${escapeHtml(title)}"
  >${escapeHtml(short)}</span>`;
}

function renderIntersectionBadges(
  narratives: CrossPollinationNarrativeRef[],
  options?: { currentNarrativeId?: number; onlyOther?: boolean }
): string {
  if (!narratives.length) return "";
  const sorted = [...narratives].sort((a, b) => a.narrative_name.localeCompare(b.narrative_name));
  const pills = sorted
    .filter((n) => {
      if (!options?.onlyOther || options.currentNarrativeId == null) return true;
      return n.narrative_id !== options.currentNarrativeId;
    })
    .map((n) =>
      renderNarrativePill(n, {
        current: options?.currentNarrativeId === n.narrative_id,
        also:
          options?.currentNarrativeId != null &&
          n.narrative_id !== options.currentNarrativeId,
      })
    )
    .join("");

  if (!pills) return "";

  const label = sorted.map((n) => n.narrative_name).join(", ");
  return `<span class="cross-narrative-pills" aria-label="Narrative overlap: ${escapeHtml(label)}">${pills}</span>`;
}

function renderNarrativeLegend(report: CrossPollinationReport): string {
  const narratives = collectNarrativesFromReport(report);
  if (narratives.length < 2) return "";
  const items = narratives
    .map((n) => renderNarrativePill(n))
    .join('<span class="cross-legend-sep" aria-hidden="true">·</span>');
  return `<div class="cross-narrative-legend" role="list" aria-label="Narrative color key">${items}</div>`;
}

function renderPairRow(pair: NarrativePairOverlap): string {
  const a: CrossPollinationNarrativeRef = {
    narrative_id: pair.narrative_a_id,
    narrative_name: pair.narrative_a_name,
    post_count: 0,
    max_outrage: null,
    first_seen: null,
    last_seen: null,
  };
  const b: CrossPollinationNarrativeRef = {
    narrative_id: pair.narrative_b_id,
    narrative_name: pair.narrative_b_name,
    post_count: 0,
    max_outrage: null,
    first_seen: null,
    last_seen: null,
  };
  return `<li class="cross-pair-item">
    <span class="cross-pair-badges">${renderNarrativePill(a)}<span class="cross-pair-link" aria-hidden="true">×</span>${renderNarrativePill(b)}</span>
    <span class="cross-pair-count">${pair.shared_actor_count} shared</span>
  </li>`;
}

export function crossPollinationPanelHtml(
  report: CrossPollinationReport | null,
  asInner = false
): string {
  const count = report?.actor_count ?? 0;
  const badge =
    count > 0
      ? `<span class="topology-badge topology-star">${count} cross-narrative actors</span>`
      : `<span class="topology-badge topology-sparse">global scan</span>`;

  const inner = `
      <h2>Narrative cross-pollination ${badge}</h2>
      <p class="chart-caption">
        Scans <strong>all narratives</strong> in heimdall.db for accounts posting in multiple keyword silos.
        <strong>Colored pills</strong> = which campaigns share each actor (hover for post counts).
      </p>
      <div id="cross-pollination-global-host"></div>
      <div id="cross-pollination-narrative-host"></div>
  `;
  if (asInner) {
    return `<div class="panel panel-cross-pollination" id="cross-pollination-panel">${inner}</div>`;
  }
  return `<section class="panel panel-cross-pollination" id="cross-pollination-panel">${inner}</section>`;
}

export function renderGlobalCrossPollination(
  host: HTMLElement,
  report: CrossPollinationReport | null
): void {
  if (!report?.available) {
    host.innerHTML = "<p class='empty'>Cross-pollination scan unavailable (no posts in database).</p>";
    return;
  }
  if (!report.actor_count) {
    host.innerHTML =
      "<p class='empty'>No actors span multiple narratives yet — ingest at least two narratives with shared accounts.</p>";
    return;
  }

  const legend = renderNarrativeLegend(report);
  const pairs = (report.narrative_pairs ?? []).slice(0, 6).map(renderPairRow).join("");

  const actors = (report.actors ?? [])
    .slice(0, 12)
    .map((a) => renderActorButton(a))
    .join("");

  host.innerHTML = `
    ${legend}
    <h3 class="cross-subhead">Top cross-narrative actors</h3>
    <div class="cross-actor-list">${actors}</div>
    ${
      pairs
        ? `<h3 class="cross-subhead">Narrative pair overlap</h3><ul class="cross-pair-list">${pairs}</ul>`
        : ""
    }
  `;

  bindActorButtons(host);
}

export function renderNarrativeCrossPollination(
  host: HTMLElement,
  hits: NarrativePollinationHits | null,
  narrativeName: string,
  currentNarrativeId?: number
): void {
  if (!hits || hits.hit_count === 0) {
    host.innerHTML = `<p class="metric-sub">No multi-narrative actors in <strong>${escapeHtml(narrativeName)}</strong> yet.</p>`;
    return;
  }

  host.innerHTML = `
    <h3 class="cross-subhead">In this narrative (${hits.hit_count} multi-silo actors)</h3>
    <p class="cross-caption-inline"><span class="cross-narr-pill-legend-hint">Pill with ring</span> = this narrative · other colors = also active elsewhere</p>
    <div class="cross-actor-list">${hits.actors
      .slice(0, 8)
      .map((a) => renderActorButton(a, { currentNarrativeId }))
      .join("")}</div>
  `;

  bindActorButtons(host);
}

function renderActorButton(
  actor: CrossPollinationActor,
  options?: { currentNarrativeId?: number }
): string {
  const label = actor.author_handle ?? actor.author_id.slice(0, 14);
  const score = actor.pollination_score.toFixed(2);

  let narratives = actor.narratives;
  if (actor.other_narratives?.length) {
    const currentId = options?.currentNarrativeId ?? hitsCurrentFromActor(actor);
    const current = narratives.find((n) => n.narrative_id === currentId);
    narratives = current
      ? [current, ...actor.other_narratives]
      : [...actor.other_narratives];
  }

  const pills = renderIntersectionBadges(narratives, {
    currentNarrativeId: options?.currentNarrativeId,
  });

  return `<button type="button" class="cross-actor-btn" data-author-id="${escapeHtml(actor.author_id)}" data-author-label="${escapeHtml(label)}">
    <div class="cross-actor-head">
      <strong class="cross-actor-handle">${escapeHtml(label)}</strong>
      ${pills}
    </div>
    <span class="cross-actor-meta">${actor.narrative_count} narratives · ${actor.total_posts} posts · score ${score}</span>
  </button>`;
}

function hitsCurrentFromActor(actor: CrossPollinationActor): number | undefined {
  if (!actor.other_narratives?.length) return undefined;
  const otherIds = new Set(actor.other_narratives.map((n) => n.narrative_id));
  const current = actor.narratives.find((n) => !otherIds.has(n.narrative_id));
  return current?.narrative_id;
}

function bindActorButtons(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>(".cross-actor-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.authorId;
      const label = btn.dataset.authorLabel ?? id;
      if (id) selectAuthor(id, `Cross-poll: ${label}`);
      window.dispatchEvent(new CustomEvent("heimdall:goto-posts"));
    });
  });
}

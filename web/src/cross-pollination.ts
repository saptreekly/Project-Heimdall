import { selectAuthor } from "./investigation";
import { escapeHtml } from "./post-display";
import type { CrossPollinationActor, CrossPollinationReport, NarrativePollinationHits } from "./types";

export function crossPollinationPanelHtml(report: CrossPollinationReport | null): string {
  const count = report?.actor_count ?? 0;
  const badge =
    count > 0
      ? `<span class="topology-badge topology-star">${count} cross-narrative actors</span>`
      : `<span class="topology-badge topology-sparse">global scan</span>`;

  return `
    <section class="panel panel-cross-pollination" id="cross-pollination-panel">
      <h2>Narrative cross-pollination ${badge}</h2>
      <p class="chart-caption">
        Scans <strong>all narratives</strong> in heimdall.db for accounts posting in multiple keyword silos.
        Persistent overlap suggests long-running proxy networks, not one-off flashpoints.
      </p>
      <div id="cross-pollination-global-host"></div>
      <div id="cross-pollination-narrative-host"></div>
    </section>
  `;
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

  const pairs = (report.narrative_pairs ?? [])
    .slice(0, 6)
    .map(
      (p) =>
        `<li><strong>${escapeHtml(p.narrative_a_name)}</strong> ↔ <strong>${escapeHtml(p.narrative_b_name)}</strong>: ${p.shared_actor_count} shared actor(s)</li>`
    )
    .join("");

  const actors = (report.actors ?? [])
    .slice(0, 12)
    .map((a) => renderActorButton(a, "global"))
    .join("");

  host.innerHTML = `
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
  narrativeName: string
): void {
  if (!hits || hits.hit_count === 0) {
    host.innerHTML = `<p class="metric-sub">No multi-narrative actors in <strong>${escapeHtml(narrativeName)}</strong> yet.</p>`;
    return;
  }

  host.innerHTML = `
    <h3 class="cross-subhead">In this narrative (${hits.hit_count} multi-silo actors)</h3>
    <div class="cross-actor-list">${hits.actors
      .slice(0, 8)
      .map((a) => renderActorButton(a as CrossPollinationActor, "narrative", a))
      .join("")}</div>
  `;

  bindActorButtons(host);
}

function renderActorButton(
  actor: CrossPollinationActor,
  _mode: string,
  hit?: CrossPollinationActor & { other_narratives?: Array<{ narrative_name: string; post_count: number }> }
): string {
  const label = actor.author_handle ?? actor.author_id.slice(0, 14);
  const silos = hit?.other_narratives
    ? hit.other_narratives.map((n) => escapeHtml(n.narrative_name)).join(", ")
    : actor.narratives.map((n) => escapeHtml(n.narrative_name)).join(", ");
  const score = actor.pollination_score.toFixed(2);
  return `<button type="button" class="cross-actor-btn" data-author-id="${escapeHtml(actor.author_id)}" data-author-label="${escapeHtml(label)}">
    <strong>${escapeHtml(label)}</strong>
    <span class="cross-actor-meta">${actor.narrative_count} narratives · ${actor.total_posts} posts · score ${score}</span>
    <span class="cross-actor-silos">${silos}</span>
  </button>`;
}

function bindActorButtons(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>(".cross-actor-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.authorId;
      const label = btn.dataset.authorLabel ?? id;
      if (id) selectAuthor(id, `Cross-poll: ${label}`);
      document.getElementById("posts-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

import {
  countMatchingPosts,
  getInvestigationFilter,
  hasActiveFilter,
} from "./investigation";
import { updateModeBadges, type ModeBadges } from "./desk-modes";

export function deskStripHtml(): string {
  return `<div id="desk-strip" class="desk-strip" hidden role="status" aria-live="polite">
    <div class="desk-strip-inner">
      <div class="desk-strip-context">
        <span class="desk-strip-label">Investigating</span>
        <strong id="desk-strip-filter-label" class="desk-strip-filter"></strong>
        <span id="desk-strip-count" class="desk-strip-count"></span>
      </div>
      <div class="desk-strip-actions">
        <button type="button" id="desk-strip-open-evidence" class="btn btn-secondary btn-small">Open Evidence</button>
        <button type="button" id="desk-strip-clear" class="btn btn-secondary btn-small">Clear filter</button>
      </div>
    </div>
  </div>`;
}

export function scrollDeskStripIntoView(): void {
  document.getElementById("desk-strip")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

export function updateDeskStrip(computeBadges: () => ModeBadges): void {
  const strip = document.getElementById("desk-strip");
  const labelEl = document.getElementById("desk-strip-filter-label");
  const countEl = document.getElementById("desk-strip-count");
  if (!strip || !labelEl || !countEl) return;

  const f = getInvestigationFilter();
  const active = hasActiveFilter() && f.label;
  strip.hidden = !active;

  if (!active) {
    document.body.classList.remove("has-desk-strip");
    updateModeBadges(computeBadges());
    return;
  }

  const matchCount = countMatchingPosts();
  labelEl.textContent = f.label;
  countEl.textContent = `${matchCount} post${matchCount === 1 ? "" : "s"}`;
  document.body.classList.add("has-desk-strip");
  updateModeBadges(computeBadges());
}

export function bindDeskStrip(onClear: () => void, onOpenEvidence: () => void): void {
  document.getElementById("desk-strip-clear")?.addEventListener("click", onClear);
  document.getElementById("desk-strip-open-evidence")?.addEventListener("click", onOpenEvidence);
}

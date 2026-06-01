import {
  countMatchingPosts,
  getInvestigationFilter,
  hasActiveFilter,
} from "../investigation";
import { updateSectionBadges, type SectionBadges } from "../analysis-sections";

export function scrollGlobalInvestigationIntoView(): void {
  document
    .getElementById("global-investigation-bar")
    ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

export function updateGlobalInvestigationBar(
  computeBadges: () => SectionBadges
): void {
  const bar = document.getElementById("global-investigation-bar");
  const labelEl = document.getElementById("global-investigation-label");
  const countEl = document.getElementById("global-investigation-count");
  if (!bar || !labelEl || !countEl) return;

  const f = getInvestigationFilter();
  const active = hasActiveFilter() && f.label;
  bar.hidden = !active;

  if (!active) {
    document.body.classList.remove("has-mobile-investigation-bar");
    updateSectionBadges(computeBadges());
    return;
  }

  const matchCount = countMatchingPosts();
  labelEl.textContent = f.label;
  countEl.textContent = `${matchCount} post${matchCount === 1 ? "" : "s"}`;
  document.body.classList.add("has-mobile-investigation-bar");
  updateSectionBadges(computeBadges());
}

export function globalInvestigationBarHtml(): string {
  return `<div id="global-investigation-bar" class="global-investigation-bar" hidden role="status">
    <span class="investigation-label">Investigating</span>
    <strong id="global-investigation-label"></strong>
    <span id="global-investigation-count" class="investigation-count"></span>
    <button type="button" id="global-clear-investigation" class="btn btn-secondary btn-small">Clear filter</button>
  </div>`;
}

export function bindGlobalInvestigationClear(onClear: () => void): void {
  document.getElementById("global-clear-investigation")?.addEventListener("click", onClear);
}

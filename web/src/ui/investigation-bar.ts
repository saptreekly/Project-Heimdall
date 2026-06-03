import {
  bindDeskStrip,
  deskStripHtml,
  scrollDeskStripIntoView,
  updateDeskStrip,
} from "../desk-strip";
import type { ModeBadges } from "../desk-modes";

export function scrollGlobalInvestigationIntoView(): void {
  scrollDeskStripIntoView();
}

export function updateGlobalInvestigationBar(computeBadges: () => ModeBadges): void {
  updateDeskStrip(computeBadges);
}

export function globalInvestigationBarHtml(): string {
  return deskStripHtml();
}

export function bindGlobalInvestigationClear(
  onClear: () => void,
  onOpenEvidence?: () => void
): void {
  bindDeskStrip(onClear, onOpenEvidence ?? (() => {}));
}

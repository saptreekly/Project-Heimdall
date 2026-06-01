export type AnalysisSection = "overview" | "signals" | "graphs" | "anomalies" | "posts";

const SECTIONS: AnalysisSection[] = ["overview", "signals", "graphs", "anomalies", "posts"];

const SECTION_LABELS: Record<AnalysisSection, string> = {
  overview: "Overview",
  signals: "Signals",
  graphs: "Graphs",
  anomalies: "Anomalies",
  posts: "Posts",
};

export type SectionBadges = Partial<Record<AnalysisSection, number | string>>;

export function analysisSectionFromUrl(): AnalysisSection {
  const s = new URLSearchParams(window.location.search).get("section");
  if (s && SECTIONS.includes(s as AnalysisSection)) return s as AnalysisSection;
  return "overview";
}

export function setAnalysisSectionInUrl(section: AnalysisSection): void {
  const url = new URL(window.location.href);
  if (section === "overview") url.searchParams.delete("section");
  else url.searchParams.set("section", section);
  window.history.replaceState({}, "", url);
}

export function renderAnalysisSectionNav(
  active: AnalysisSection,
  badges?: SectionBadges
): string {
  const buttons = SECTIONS.map((id) => {
    const badgeVal = badges?.[id];
    const showBadge =
      badgeVal !== undefined &&
      badgeVal !== "" &&
      badgeVal !== 0 &&
      badgeVal !== "0";
    const badge = showBadge
      ? `<span class="section-badge" aria-label="${badgeVal} items">${badgeVal}</span>`
      : "";
    return `<button type="button" class="analysis-section-btn${id === active ? " analysis-section-active" : ""}" data-analysis-section="${id}" aria-current="${id === active ? "page" : "false"}">${SECTION_LABELS[id]}${badge}</button>`;
  }).join("");
  return `<nav class="analysis-section-nav" role="navigation" aria-label="Analysis sections">${buttons}</nav>`;
}

export function updateSectionBadges(badges: SectionBadges): void {
  for (const id of SECTIONS) {
    const btn = document.querySelector<HTMLButtonElement>(`[data-analysis-section="${id}"]`);
    if (!btn) continue;
    const existing = btn.querySelector(".section-badge");
    existing?.remove();
    const badgeVal = badges[id];
    const showBadge =
      badgeVal !== undefined &&
      badgeVal !== "" &&
      badgeVal !== 0 &&
      badgeVal !== "0";
    if (showBadge) {
      btn.insertAdjacentHTML(
        "beforeend",
        `<span class="section-badge" aria-label="${badgeVal} items">${badgeVal}</span>`
      );
    }
  }
}

export function bindAnalysisSectionNav(onChange: (section: AnalysisSection) => void): void {
  document.querySelectorAll<HTMLButtonElement>("[data-analysis-section]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const section = btn.dataset.analysisSection as AnalysisSection;
      onChange(section);
    });
  });
}

export function showAnalysisSection(section: AnalysisSection): void {
  document.querySelectorAll<HTMLElement>("[data-analysis-section-panel]").forEach((el) => {
    const id = el.dataset.analysisSectionPanel as AnalysisSection;
    el.toggleAttribute("hidden", id !== section);
  });
  document.querySelectorAll<HTMLButtonElement>("[data-analysis-section]").forEach((btn) => {
    const active = btn.dataset.analysisSection === section;
    btn.classList.toggle("analysis-section-active", active);
    btn.setAttribute("aria-current", active ? "page" : "false");
  });
}

/** Collapsible panel wrapper — closed by default unless `open` is true. */
export function panelRollupHtml(summary: string, bodyHtml: string, open = false): string {
  return `<details class="panel-rollup"${open ? " open" : ""}>
    <summary class="panel-rollup-summary">${summary}</summary>
    <div class="panel-rollup-body">${bodyHtml}</div>
  </details>`;
}

export function analysisLayoutHtml(
  sectionPanelsHtml: string,
  activeSection: AnalysisSection,
  badges?: SectionBadges
): string {
  return `
    <div class="analysis-layout">
      <aside class="analysis-rail" id="analysis-rail" aria-label="Analysis navigation">
        ${renderAnalysisSectionNav(activeSection, badges)}
      </aside>
      <div class="analysis-main">
        ${sectionPanelsHtml}
      </div>
    </div>
  `;
}

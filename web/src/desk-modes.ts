export type DeskMode = "pulse" | "frames" | "evidence" | "network";

const MODES: DeskMode[] = ["pulse", "frames", "evidence", "network"];

const MODE_META: Record<
  DeskMode,
  { title: string; hint: string; shortcut: string; icon: string }
> = {
  pulse: { title: "Pulse", hint: "Metrics & alerts", shortcut: "1", icon: "1" },
  frames: { title: "Frames", hint: "Theme clusters", shortcut: "2", icon: "2" },
  evidence: { title: "Evidence", hint: "Post stream", shortcut: "3", icon: "3" },
  network: { title: "Network", hint: "Graph & coordination", shortcut: "4", icon: "4" },
};

const LEGACY_SECTION_MAP: Record<string, DeskMode> = {
  overview: "pulse",
  signals: "pulse",
  graphs: "network",
  anomalies: "network",
  posts: "evidence",
};

export type ModeBadges = Partial<Record<DeskMode, number | string>>;

/** @deprecated use ModeBadges */
export type SectionBadges = ModeBadges;

export function deskModeFromUrl(): DeskMode {
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("mode");
  if (mode && MODES.includes(mode as DeskMode)) return mode as DeskMode;
  const legacy = params.get("section");
  if (legacy && LEGACY_SECTION_MAP[legacy]) return LEGACY_SECTION_MAP[legacy];
  return "pulse";
}

export function setDeskModeInUrl(mode: DeskMode): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("section");
  if (mode === "pulse") url.searchParams.delete("mode");
  else url.searchParams.set("mode", mode);
  window.history.replaceState({}, "", url);
}

export function renderDeskModeRail(active: DeskMode, badges?: ModeBadges): string {
  const buttons = MODES.map((id) => {
    const meta = MODE_META[id];
    const badgeVal = badges?.[id];
    const showBadge =
      badgeVal !== undefined && badgeVal !== "" && badgeVal !== 0 && badgeVal !== "0";
    const badge = showBadge
      ? `<span class="desk-mode-badge" aria-label="${badgeVal} items">${badgeVal}</span>`
      : "";
    return `<button type="button" class="desk-mode-btn${id === active ? " desk-mode-active" : ""}" data-desk-mode="${id}" aria-current="${id === active ? "page" : "false"}" title="${meta.hint} · key ${meta.shortcut}">
      <span class="desk-mode-index" aria-hidden="true">${meta.icon}</span>
      <span class="desk-mode-text">
        <span class="desk-mode-label">${meta.title}</span>
        <span class="desk-mode-hint">${meta.hint}</span>
      </span>
      ${badge}
    </button>`;
  }).join("");
  return `<nav class="desk-rail-nav" role="navigation" aria-label="Desk modes">${buttons}</nav>`;
}

export function updateModeBadges(badges: ModeBadges): void {
  for (const id of MODES) {
    const btn = document.querySelector<HTMLButtonElement>(`[data-desk-mode="${id}"]`);
    if (!btn) continue;
    btn.querySelector(".desk-mode-badge")?.remove();
    const badgeVal = badges[id];
    const showBadge =
      badgeVal !== undefined && badgeVal !== "" && badgeVal !== 0 && badgeVal !== "0";
    if (showBadge) {
      btn.insertAdjacentHTML(
        "beforeend",
        `<span class="desk-mode-badge" aria-label="${badgeVal} items">${badgeVal}</span>`
      );
    }
  }
}

/** @deprecated use updateModeBadges */
export const updateSectionBadges = updateModeBadges;

export function bindDeskModeNav(onChange: (mode: DeskMode) => void): void {
  document.querySelectorAll<HTMLButtonElement>("[data-desk-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.deskMode as DeskMode;
      onChange(mode);
    });
  });
}

export function showDeskMode(mode: DeskMode): void {
  document.querySelectorAll<HTMLElement>("[data-desk-mode-panel]").forEach((el) => {
    const id = el.dataset.deskModePanel as DeskMode;
    el.toggleAttribute("hidden", id !== mode);
  });
  document.querySelectorAll<HTMLButtonElement>("[data-desk-mode]").forEach((btn) => {
    const active = btn.dataset.deskMode === mode;
    btn.classList.toggle("desk-mode-active", active);
    btn.setAttribute("aria-current", active ? "page" : "false");
  });
  document.body.dataset.deskMode = mode;
}

export function deskLayoutHtml(
  modePanelsHtml: string,
  activeMode: DeskMode,
  badges?: ModeBadges
): string {
  return `
    <div class="desk-shell">
      <aside class="desk-rail" id="desk-rail" aria-label="Desk navigation">
        ${renderDeskModeRail(activeMode, badges)}
      </aside>
      <div class="desk-workspace">
        <main class="desk-canvas" id="desk-canvas">
          ${modePanelsHtml}
        </main>
        <aside class="desk-inspector" id="desk-inspector" aria-label="Inspector">
          <header class="desk-inspector-header">
            <h2 class="desk-inspector-title">Inspector</h2>
            <p class="desk-inspector-sub" id="desk-inspector-sub">Select a frame, author, or cluster</p>
          </header>
          <div class="desk-inspector-body" id="desk-inspector-body">
            <p class="desk-inspector-empty">Nothing selected yet. Pick a theme in <strong>Frames</strong>, an author in <strong>Network</strong>, or follow an alert from <strong>Pulse</strong>.</p>
          </div>
        </aside>
      </div>
    </div>
  `;
}

/** Collapsible panel wrapper — closed by default unless `open` is true. */
export function panelRollupHtml(summary: string, bodyHtml: string, open = false): string {
  return `<details class="panel-rollup"${open ? " open" : ""}>
    <summary class="panel-rollup-summary">${summary}</summary>
    <div class="panel-rollup-body">${bodyHtml}</div>
  </details>`;
}

export function deskModeList(): DeskMode[] {
  return [...MODES];
}

export function deskModeShortcut(mode: DeskMode): string {
  return MODE_META[mode].shortcut;
}

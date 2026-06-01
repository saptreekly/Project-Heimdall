export type AppTab = "analysis" | "brief" | "methodology";

const TABS: AppTab[] = ["analysis", "brief", "methodology"];

const TAB_PANEL_IDS: Record<AppTab, string> = {
  analysis: "panel-analysis",
  brief: "panel-brief",
  methodology: "panel-methodology",
};

const TAB_BUTTON_IDS: Record<AppTab, string> = {
  analysis: "tab-analysis",
  brief: "tab-brief",
  methodology: "tab-methodology",
};

export function tabFromUrl(): AppTab {
  const t = new URLSearchParams(window.location.search).get("tab");
  if (t === "methodology") return "methodology";
  if (t === "brief") return "brief";
  return "analysis";
}

export function setTabInUrl(tab: AppTab): void {
  const url = new URL(window.location.href);
  if (tab === "analysis") url.searchParams.delete("tab");
  else url.searchParams.set("tab", tab);
  window.history.replaceState({}, "", url);
}

export function renderTabNav(active: AppTab): string {
  const buttons = TABS.map((tab) => {
    const label = tab === "analysis" ? "Analysis" : tab === "brief" ? "Briefing" : "Methodology";
    return `<button type="button" role="tab" id="${TAB_BUTTON_IDS[tab]}" data-tab="${tab}" aria-selected="${active === tab}" aria-controls="${TAB_PANEL_IDS[tab]}" tabindex="${active === tab ? "0" : "-1"}">${label}</button>`;
  }).join("");
  return `
    <nav class="tab-nav" role="tablist" aria-label="Dashboard sections">
      ${buttons}
    </nav>
  `;
}

function focusTab(tab: AppTab): void {
  document.getElementById(TAB_BUTTON_IDS[tab])?.focus();
}

export function bindTabNav(onChange: (tab: AppTab) => void): void {
  const tablist = document.querySelector(".tab-nav");
  if (!tablist) return;

  tablist.querySelectorAll<HTMLButtonElement>("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab as AppTab;
      onChange(tab);
    });
  });

  tablist.addEventListener("keydown", (e) => {
    const ev = e as KeyboardEvent;
    const target = ev.target as HTMLElement;
    if (target.getAttribute("role") !== "tab") return;
    const current = target.dataset.tab as AppTab;
    const idx = TABS.indexOf(current);
    if (idx < 0) return;

    let next: AppTab | null = null;
    if (ev.key === "ArrowRight") next = TABS[(idx + 1) % TABS.length]!;
    else if (ev.key === "ArrowLeft") next = TABS[(idx - 1 + TABS.length) % TABS.length]!;
    else if (ev.key === "Home") next = TABS[0]!;
    else if (ev.key === "End") next = TABS[TABS.length - 1]!;
    else return;

    ev.preventDefault();
    onChange(next);
    focusTab(next);
  });
}

export function showTabPanel(tab: AppTab): void {
  for (const t of TABS) {
    const panel = document.getElementById(TAB_PANEL_IDS[t]);
    const isActive = t === tab;
    panel?.toggleAttribute("hidden", !isActive);
    panel?.setAttribute("role", "tabpanel");
    panel?.setAttribute("aria-labelledby", TAB_BUTTON_IDS[t]);
    if (isActive) panel?.removeAttribute("tabindex");
    else panel?.setAttribute("tabindex", "-1");
  }

  document.querySelectorAll<HTMLButtonElement>(".tab-nav [data-tab]").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("tab-active", active);
    btn.setAttribute("aria-selected", String(active));
    btn.setAttribute("tabindex", active ? "0" : "-1");
  });
}

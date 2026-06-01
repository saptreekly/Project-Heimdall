export type AppTab = "analysis" | "brief" | "methodology";

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
  return `
    <nav class="tab-nav" role="tablist" aria-label="Dashboard sections">
      <button type="button" role="tab" id="tab-analysis" data-tab="analysis" aria-selected="${active === "analysis"}">Analysis</button>
      <button type="button" role="tab" id="tab-brief" data-tab="brief" aria-selected="${active === "brief"}">Briefing</button>
      <button type="button" role="tab" id="tab-methodology" data-tab="methodology" aria-selected="${active === "methodology"}">Methodology</button>
    </nav>
  `;
}

export function bindTabNav(onChange: (tab: AppTab) => void): void {
  document.querySelectorAll<HTMLButtonElement>(".tab-nav [data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab as AppTab;
      onChange(tab);
    });
  });
}

export function showTabPanel(tab: AppTab): void {
  const analysis = document.getElementById("panel-analysis");
  const brief = document.getElementById("panel-brief");
  const methodology = document.getElementById("panel-methodology");

  analysis?.toggleAttribute("hidden", tab !== "analysis");
  brief?.toggleAttribute("hidden", tab !== "brief");
  methodology?.toggleAttribute("hidden", tab !== "methodology");

  document.querySelectorAll<HTMLButtonElement>(".tab-nav [data-tab]").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("tab-active", active);
    btn.setAttribute("aria-selected", String(active));
  });
}

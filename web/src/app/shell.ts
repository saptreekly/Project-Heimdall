import { renderContentNotice } from "../content-notice";
import { renderDataAsOfHtml, renderDataLinksExtra, renderRateFooter } from "../dashboard-meta";
import { briefPanelHtml } from "../brief";
import { renderMethodology } from "../methodology";
import { renderTabNav } from "../tabs";
import { renderOnboardingHintHtml } from "../onboarding-hint";
import { globalInvestigationBarHtml, stateLoadingHtml } from "../ui";
import { escapeHtml } from "../post-display";
import type { NarrativeSummary } from "../types";
import { appState } from "./state";

export function shell(
  narratives: NarrativeSummary[],
  selectedId: number,
  generatedAt: string | null
): string {
  const options = narratives
    .map(
      (n) =>
        `<option value="${n.id}" ${n.id === selectedId ? "selected" : ""}>${escapeHtml(n.name)} (${n.post_count} posts)</option>`
    )
    .join("");
  const stamp = generatedAt ? ` · ${escapeHtml(generatedAt.slice(0, 19))} UTC` : "";
  return `
    <div class="app">
      <header class="site-header">
        <div class="header-top">
          <h1><span class="brand">Heimdall</span> Narrative Desk</h1>
          <p class="data-badge">Repo snapshot${stamp}</p>
          <button type="button" id="open-methodology-drawer" class="btn btn-secondary btn-small header-methodology-btn" title="Methods &amp; limitations">Methodology</button>
        </div>
        ${renderContentNotice()}
        ${renderOnboardingHintHtml()}
        <details class="header-meta-collapse">
          <summary class="header-meta-summary">Data sources &amp; ingest</summary>
          <p class="data-links">Source data: ${renderDataLinksExtra()}</p>
          ${renderRateFooter()}
        </details>
      </header>
      ${renderTabNav(appState.currentTab)}
      <div id="panel-analysis" role="tabpanel" aria-labelledby="tab-analysis"${appState.currentTab !== "analysis" ? " hidden" : ""}>
        <div class="toolbar">
          <div class="toolbar-inner">
            <fieldset class="toolbar-group">
              <legend>Data</legend>
              <label for="narrative-select">Narrative</label>
              <select id="narrative-select" class="narrative-select">${options}</select>
              ${renderDataAsOfHtml(generatedAt)}
            </fieldset>
            <fieldset class="toolbar-group">
              <legend>Display</legend>
              <label for="time-range-select" class="toolbar-label">Window</label>
              <select id="time-range-select" class="toolbar-select" aria-label="Time window">
                <option value="">All time</option>
                <option value="24">Last 24h</option>
                <option value="72">Last 72h</option>
                <option value="168">Last 7d</option>
              </select>
              <label class="toolbar-check"><input type="checkbox" id="group-authors-toggle" checked /> Group busy authors</label>
              <label class="toolbar-check"><input type="checkbox" id="blur-sensitive-toggle" ${appState.blurSensitive ? "checked" : ""} /> Blur sensitive text</label>
              <label class="toolbar-check"><input type="checkbox" id="compact-charts-toggle" ${appState.compactCharts ? "checked" : ""} /> Compact charts</label>
            </fieldset>
            <fieldset class="toolbar-group toolbar-group-actions">
              <legend>Actions</legend>
              <button type="button" id="refresh-btn" class="btn btn-secondary" title="Re-fetch snapshot.json from this site — does not pull new social data until CI publishes a new export">Refresh snapshot file</button>
              <button type="button" id="goto-brief-btn" class="btn btn-secondary">Export briefing</button>
            </fieldset>
          </div>
        </div>
        <main id="content" class="dashboard desk-dashboard">${stateLoadingHtml()}</main>
        ${globalInvestigationBarHtml()}
      </div>
      <div id="panel-brief" class="panel-brief" role="tabpanel" aria-labelledby="tab-brief"${appState.currentTab !== "brief" ? " hidden" : ""}>
        <main class="dashboard">${briefPanelHtml(generatedAt)}</main>
      </div>
      <div id="panel-methodology" class="panel-methodology" role="tabpanel" aria-labelledby="tab-methodology"${appState.currentTab !== "methodology" ? " hidden" : ""}>
        <main class="dashboard prose-wrap">${renderMethodology()}</main>
      </div>
      <div id="methodology-drawer-backdrop" class="methodology-drawer-backdrop" hidden></div>
      <aside id="methodology-drawer" class="methodology-drawer" hidden aria-label="Methodology">
        <header class="methodology-drawer-header">
          <h2>Methodology</h2>
          <button type="button" id="close-methodology-drawer" class="btn btn-secondary btn-small">Close</button>
        </header>
        <div class="methodology-drawer-body prose-wrap">${renderMethodology()}</div>
      </aside>
    </div>
  `;
}

export function renderMissingSnapshot(message: string, dataLinksPublish: string): string {
  return `
    <header class="site-header">
      <h1><span class="brand">Heimdall</span> Narrative Analysis</h1>
      ${renderContentNotice()}
    </header>
    <main>
      <div class="state-error">
        <strong>Dashboard data not yet published</strong>
        <p>${escapeHtml(message)}</p>
        <p class="state-hint">This site reads a frozen snapshot file updated by automated ingest. Check back after the next deploy, or ask a maintainer for status.</p>
        <details class="maintainer-details">
          <summary>For maintainers</summary>
          <p class="sub">Publish ingest to the repo with <code>python scripts/publish_dashboard_data.py</code>, then redeploy Pages.</p>
          <p class="data-links">
            <a href="${dataLinksPublish}" target="_blank" rel="noopener">data/dashboard/README.md</a>
          </p>
        </details>
      </div>
    </main>
  `;
}

import { escapeHtml, truncate } from "./post-display";
import type {
  AmplificationReport,
  CibReport,
  DuplicateCluster,
  NarrativeSummary,
  Post,
  ThemesReport,
} from "./types";

export function briefPanelHtml(): string {
  return `
    <section class="panel panel-brief" id="brief-panel">
      <h2>Briefing</h2>
      <p class="chart-caption">One-page summary for sharing — print or copy from this panel.</p>
      <div id="brief-content" class="brief-content"></div>
      <button type="button" id="brief-print" class="btn btn-secondary btn-small">Print briefing</button>
    </section>
  `;
}

export function renderBrief(
  host: HTMLElement,
  narrative: NarrativeSummary,
  posts: Post[],
  cib: CibReport,
  amp: AmplificationReport,
  themes: ThemesReport
): void {
  const burst = amp.clusters.filter((c) => c.burst_synchronized).slice(0, 2);
  const exact = amp.clusters.filter((c) => !c.burst_synchronized).slice(0, 3);
  const emerging = (themes.timeline ?? themes.clusters)
    .filter((t) => t.emerging_theme)
    .slice(0, 3);

  host.innerHTML = `
    <article class="brief-article">
      <h3>${escapeHtml(narrative.name)}</h3>
      <p><strong>${posts.length}</strong> posts in snapshot · CIB suspicion <strong>${cib.suspicion_score.toFixed(2)}</strong> · ${cib.edge_count} graph edges</p>
      ${
        cib.iu_astroturf
          ? `<p>IU astroturf overlap: ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors.</p>`
          : ""
      }
      <h4>Exact duplicate text</h4>
      ${exact.length ? exact.map(clusterLine).join("") : "<p>None in this snapshot.</p>"}
      <h4>Synchronized bursts</h4>
      ${burst.length ? burst.map(clusterLine).join("") : "<p>None (need ≥5 authors in 90s).</p>"}
      <h4>Emerging themes</h4>
      ${
        emerging.length
          ? `<ul>${emerging
              .map(
                (t) =>
                  `<li>${escapeHtml((t.label_terms ?? []).slice(0, 5).join(", "))} (${"size" in t ? t.size : "?"} posts)</li>`
              )
              .join("")}</ul>`
          : "<p>No emerging themes flagged.</p>"
      }
      <h4>Top signals</h4>
      ${
        cib.signals.length
          ? `<ul>${cib.signals.slice(0, 6).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
          : "<p>No elevated CIB signals.</p>"
      }
    </article>
  `;
}

function clusterLine(c: DuplicateCluster): string {
  return `<p class="brief-cluster"><strong>${c.count} posts</strong> · ${c.author_count} author(s) — ${escapeHtml(truncate(c.sample_text, 120))}</p>`;
}

export function bindBriefPrint(): void {
  document.getElementById("brief-print")?.addEventListener("click", () => {
    window.print();
  });
}

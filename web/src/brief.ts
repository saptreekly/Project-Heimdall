import { escapeHtml, truncate } from "./post-display";
import type {
  AmplificationReport,
  CibReport,
  CrossAuthorFuzzyCluster,
  CrossPollinationActor,
  CrossPollinationReport,
  DuplicateCluster,
  NarrativeSummary,
  NearDuplicatesReport,
  Post,
  ThemesReport,
} from "./types";

const BRIEF_COPY_LABEL = "Copy as Markdown Briefing";
const BRIEF_COPIED_LABEL = "Copied!";

export function briefPanelHtml(generatedAt: string | null = null): string {
  const asOf = generatedAt
    ? `<p class="brief-data-as-of">Snapshot data as of <strong>${escapeHtml(generatedAt.slice(0, 19))} UTC</strong></p>`
    : "";
  return `
    <section class="panel panel-brief" id="brief-panel">
      <h2>Briefing</h2>
      ${asOf}
      <p class="chart-caption">One-page summary for sharing — print, or copy Markdown for secure wires and wikis.</p>
      <div id="brief-content" class="brief-content"></div>
      <div class="brief-actions">
        <button type="button" id="brief-print" class="btn btn-secondary btn-small">Print briefing</button>
        <button type="button" id="brief-copy-clip" class="btn btn-secondary btn-small">${BRIEF_COPY_LABEL}</button>
      </div>
    </section>
  `;
}

export function renderBrief(
  host: HTMLElement,
  narrative: NarrativeSummary,
  posts: Post[],
  cib: CibReport,
  amp: AmplificationReport,
  themes: ThemesReport,
  nearDup?: NearDuplicatesReport | null,
  crossPollination?: CrossPollinationReport | null
): void {
  const burst = amp.clusters.filter((c) => c.burst_synchronized).slice(0, 2);
  const exact = amp.clusters.filter((c) => !c.burst_synchronized).slice(0, 3);
  const emerging = (themes.timeline ?? themes.clusters)
    .filter((t) => t.emerging_theme)
    .slice(0, 3);
  const fuzzy = (nearDup?.cross_author_fuzzy ?? []).slice(0, 3);

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
      <h4>Synchronized bursts (exact text)</h4>
      ${burst.length ? burst.map(clusterLine).join("") : "<p>None (need ≥5 authors in 90s).</p>"}
      <h4>Cross-author fuzzy amplification</h4>
      ${fuzzy.length ? fuzzy.map(fuzzyLine).join("") : "<p>None (Jaccard variants across ≥2 authors).</p>"}
      <h4>Cross-narrative actors (global)</h4>
      ${
        (crossPollination?.actors ?? []).length
          ? (crossPollination!.actors.slice(0, 5).map(
              (a) =>
                `<p class="brief-cluster"><strong>${escapeHtml(a.author_handle ?? a.author_id)}</strong> · ${a.narrative_count} narratives · score ${a.pollination_score.toFixed(2)}</p>`
            ).join(""))
          : "<p>None spanning multiple narratives.</p>"
      }
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

  bindBriefClipboard(
    buildBriefMarkdown(
      narrative,
      posts,
      cib,
      exact,
      burst,
      fuzzy,
      crossPollination ?? null,
      emerging
    )
  );
}

function buildBriefMarkdown(
  narrative: NarrativeSummary,
  posts: Post[],
  cib: CibReport,
  exact: DuplicateCluster[],
  burst: DuplicateCluster[],
  fuzzy: CrossAuthorFuzzyCluster[],
  crossPollination: CrossPollinationReport | null,
  emerging: Array<{ label_terms?: string[]; emerging_theme?: boolean; size?: number }>
): string {
  const lines: string[] = [];
  const stamp = new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC";

  lines.push(`# Heimdall briefing — ${mdPlain(narrative.name)}`);
  lines.push("");
  lines.push(`> Tactical snapshot · ${stamp}`);
  lines.push("");
  lines.push("## Target metrics");
  lines.push("");
  lines.push(`| Metric | Value |`);
  lines.push(`| --- | --- |`);
  lines.push(`| Posts in snapshot | **${posts.length}** |`);
  lines.push(`| CIB suspicion score | **${cib.suspicion_score.toFixed(2)}** |`);
  lines.push(`| Organic score | ${cib.organic_score.toFixed(2)} |`);
  lines.push(`| Graph nodes / edges | ${cib.node_count} / ${cib.edge_count} |`);
  lines.push(`| Graph density | ${cib.density.toFixed(3)} |`);
  if (cib.iu_astroturf) {
    lines.push(
      `| IU astroturf overlap | ${cib.iu_astroturf.known_political_bots} known bots / ${cib.iu_astroturf.authors_in_narrative} authors |`
    );
  }
  lines.push("");

  lines.push("## CIB warning signals");
  lines.push("");
  if (cib.signals.length) {
    for (const s of cib.signals.slice(0, 6)) {
      lines.push(`- ${mdPlain(s)}`);
    }
  } else {
    lines.push("_No elevated CIB signals in this snapshot._");
  }
  lines.push("");

  lines.push("## Exact duplicate text");
  lines.push("");
  if (exact.length) {
    for (const c of exact) lines.push(mdClusterBullet(c));
  } else {
    lines.push("_None in this snapshot._");
  }
  lines.push("");

  lines.push("## Synchronized bursts (exact text)");
  lines.push("");
  if (burst.length) {
    for (const c of burst) lines.push(mdClusterBullet(c));
  } else {
    lines.push("_None (need ≥5 authors in 90s window)._");
  }
  lines.push("");

  lines.push("## Cross-author fuzzy amplification");
  lines.push("");
  if (fuzzy.length) {
    for (const c of fuzzy) {
      const pct = (c.max_similarity * 100).toFixed(0);
      lines.push(
        `- **${c.count} posts** · ${c.author_count} authors · ~${pct}% Jaccard — ${mdPlain(truncate(c.sample_text, 200))}`
      );
    }
  } else {
    lines.push("_None (Jaccard variants across ≥2 authors)._");
  }
  lines.push("");

  lines.push("## Cross-narrative actors (global)");
  lines.push("");
  const actors = (crossPollination?.actors ?? []).slice(0, 5);
  if (actors.length) {
    for (const a of actors) lines.push(mdPollinationBullet(a));
  } else {
    lines.push("_None spanning multiple narratives._");
  }
  lines.push("");

  lines.push("## Emerging themes");
  lines.push("");
  if (emerging.length) {
    for (const t of emerging) {
      const terms = (t.label_terms ?? []).slice(0, 5).join(", ");
      const size = "size" in t && t.size != null ? t.size : "?";
      lines.push(`- ${mdPlain(terms)} (${size} posts)`);
    }
  } else {
    lines.push("_No emerging themes flagged._");
  }
  lines.push("");
  lines.push("---");
  lines.push("_Exported from Heimdall · verify against live snapshot before operational use._");

  return lines.join("\n");
}

function mdClusterBullet(c: DuplicateCluster): string {
  return `- **${c.count} posts** · ${c.author_count} author(s) — ${mdPlain(truncate(c.sample_text, 200))}`;
}

function mdPollinationBullet(a: CrossPollinationActor): string {
  const label = a.author_handle ?? a.author_id;
  const silos = a.narratives.map((n) => n.narrative_name).join(", ");
  return `- **${mdPlain(label)}** · ${a.narrative_count} narratives (${mdPlain(silos)}) · score ${a.pollination_score.toFixed(2)} · ${a.total_posts} posts`;
}

function mdPlain(text: string): string {
  return text.replace(/\r?\n/g, " ").replace(/\|/g, "\\|").trim();
}

function clusterLine(c: DuplicateCluster): string {
  return `<p class="brief-cluster"><strong>${c.count} posts</strong> · ${c.author_count} author(s) — ${escapeHtml(truncate(c.sample_text, 120))}</p>`;
}

function fuzzyLine(c: CrossAuthorFuzzyCluster): string {
  const pct = (c.max_similarity * 100).toFixed(0);
  return `<p class="brief-cluster"><strong>${c.count} posts</strong> · ${c.author_count} authors · ~${pct}% Jaccard — ${escapeHtml(truncate(c.sample_text, 120))}</p>`;
}

const briefClipboard = { markdown: "", bound: false };

export function bindBriefClipboard(markdownContent: string): void {
  briefClipboard.markdown = markdownContent;
  const btn = document.getElementById("brief-copy-clip");
  if (!btn || briefClipboard.bound) return;

  briefClipboard.bound = true;
  btn.addEventListener("click", async () => {
    const el = btn as HTMLButtonElement;
    try {
      await navigator.clipboard.writeText(briefClipboard.markdown);
      el.textContent = BRIEF_COPIED_LABEL;
      el.classList.add("brief-copy-done");
      window.setTimeout(() => {
        el.textContent = BRIEF_COPY_LABEL;
        el.classList.remove("brief-copy-done");
      }, 2200);
    } catch (err) {
      console.error("Clipboard copy rejected", err);
      el.textContent = "Copy failed";
      window.setTimeout(() => {
        el.textContent = BRIEF_COPY_LABEL;
      }, 2200);
    }
  });
}

export function bindBriefPrint(): void {
  document.getElementById("brief-print")?.addEventListener("click", () => {
    window.print();
  });
}

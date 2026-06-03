import { escapeHtml, truncate } from "./post-display";
import { labelList } from "./safe-text";
import type {
  AmplificationReport,
  CibReport,
  CrossAuthorFuzzyCluster,
  CrossPollinationActor,
  CrossPollinationReport,
  DuplicateCluster,
  NarrativeBrief,
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
      <p class="chart-caption">
        Auto-regenerated on every snapshot export — scales with corpus growth.
        Print, copy Markdown, or open committed briefs in <code>data/dashboard/briefs/</code>.
      </p>
      <div id="brief-content" class="brief-content"></div>
      <div class="brief-actions">
        <button type="button" id="brief-print" class="btn btn-secondary btn-small">Print briefing</button>
        <button type="button" id="brief-copy-clip" class="btn btn-secondary btn-small">${BRIEF_COPY_LABEL}</button>
        <a id="brief-download-md" class="btn btn-secondary btn-small brief-download" href="#" download hidden>Download .md</a>
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
  crossPollination?: CrossPollinationReport | null,
  exported?: NarrativeBrief | null
): void {
  if (exported?.markdown) {
    host.innerHTML = renderBriefFromExport(exported);
    bindBriefClipboard(exported.markdown);
    bindBriefDownload(exported);
    return;
  }

  const burst = amp.clusters.filter((c) => c.burst_synchronized).slice(0, 2);
  const exact = amp.clusters.filter((c) => !c.burst_synchronized).slice(0, 3);
  const emerging = (themes.timeline ?? themes.clusters)
    .filter((t) => t.emerging_theme)
    .slice(0, 3);
  const fuzzy = (nearDup?.cross_author_fuzzy ?? []).slice(0, 3);

  host.innerHTML = `
    <article class="brief-article">
      <p class="brief-legacy-note chart-caption">Legacy client-rendered brief — re-export snapshot for the full automated briefing.</p>
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
                  `<li>${escapeHtml(
                    [...labelList(t.label_phrases), ...labelList(t.label_terms)]
                      .slice(0, 5)
                      .join(", ") || `cluster ${t.cluster_id}`
                  )} (${"size" in t ? t.size : "?"} posts)</li>`
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

function renderBriefFromExport(brief: NarrativeBrief): string {
  const sections = brief.sections ?? {};
  const corpus = sections.corpus ?? {};
  const ingest = sections.ingest_yield ?? {};
  const sightings = sections.sightings ?? {};
  const sentiment = sections.sentiment ?? {};
  const frames = sections.coordination_frames ?? [];
  const exact = sections.exact_duplicates ?? [];
  const burst = sections.bursts ?? [];
  const fuzzy = sections.fuzzy ?? [];
  const emerging = sections.emerging_themes ?? [];
  const signals = sections.signals ?? [];
  const narrativeActors = sections.cross_pollination_narrative ?? [];
  const globalActors = sections.cross_pollination_global ?? [];
  const meta = brief.meta;
  const totals = brief.meta.totals ?? {};

  return `
    <article class="brief-article">
      <h3>${escapeHtml(meta.narrative_name)}</h3>
      <p class="brief-corpus-line">
        <strong>${meta.posts_total_db}</strong> posts in database
        · ${meta.posts_in_snapshot} in snapshot cohort
        ${meta.posts_truncated ? " · <span class='provenance-warn'>truncated cohort</span>" : ""}
      </p>
      <dl class="brief-metrics">
        <div><dt>CIB suspicion</dt><dd>${Number(corpus.cib_suspicion ?? 0).toFixed(2)}</dd></div>
        <div><dt>Text coordination</dt><dd>${Number(corpus.text_coordination ?? 0).toFixed(2)}</dd></div>
        <div><dt>Distinct themes</dt><dd>${corpus.distinct_themes ?? "—"}</dd></div>
        <div><dt>Duplicate clusters</dt><dd>${totals.exact_duplicate_clusters ?? "—"}</dd></div>
      </dl>

      ${
        Number(sightings.total_resightings) > 0
          ? `<section class="brief-section"><h4>Ingest activity</h4><p>${sightings.total_resightings} re-sightings · ${sightings.total_net_new ?? 0} net-new logged at ingest.</p></section>`
          : ""
      }
      ${
        ingest.available
          ? `<section class="brief-section"><h4>Ingest yield (${ingest.window_days}d)</h4><p>${ingest.runs} runs · ${ingest.net_new} net-new · ${ingest.duplicates} re-seen · duplicate rate ${(Number(ingest.duplicate_rate) * 100).toFixed(0)}%</p></section>`
          : ""
      }
      ${
        sentiment.trend
          ? `<section class="brief-section"><h4>Sentiment</h4><p>Trend: <strong>${escapeHtml(String(sentiment.trend))}</strong>${sentiment.week_over_week_alert ? ` · alert: ${escapeHtml(String(sentiment.week_over_week_alert))}` : ""}</p></section>`
          : ""
      }

      ${
        frames.length
          ? `<section class="brief-section"><h4>Layered coordination</h4><ul class="brief-frame-list">${frames
              .map(
                (frame) =>
                  `<li><span class="coord-tier-badge coord-tier-${escapeHtml(frame.tier ?? "context")}">${escapeHtml(frame.tier_label ?? "")}</span> ${escapeHtml(frame.label ?? "")} · ${frame.unique_post_count ?? "?"} posts · ${frame.unique_author_count ?? "?"} authors</li>`
              )
              .join("")}</ul></section>`
          : ""
      }

      <section class="brief-section"><h4>Top signals</h4>${
        signals.length
          ? `<ul>${signals.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
          : "<p>No elevated CIB signals.</p>"
      }</section>

      <section class="brief-section"><h4>Exact duplicate text</h4>${
        exact.length ? exact.map(clusterLine).join("") : "<p>None in full-database scan.</p>"
      }${moreNote(totals.exact_duplicate_clusters, exact.length)}</section>

      <section class="brief-section"><h4>Synchronized bursts</h4>${
        burst.length ? burst.map(clusterLine).join("") : "<p>None (need ≥5 authors in 90s).</p>"
      }${moreNote(totals.burst_clusters, burst.length)}</section>

      <section class="brief-section"><h4>Cross-author fuzzy amplification</h4>${
        fuzzy.length ? fuzzy.map(fuzzyLine).join("") : "<p>None in snapshot cohort.</p>"
      }${moreNote(totals.fuzzy_clusters, fuzzy.length)}</section>

      <section class="brief-section"><h4>Cross-narrative actors (narrative)</h4>${renderActorList(narrativeActors)}</section>
      <section class="brief-section"><h4>Cross-narrative actors (global)</h4>${renderActorList(globalActors, true)}</section>

      <section class="brief-section"><h4>Emerging themes</h4>${
        emerging.length
          ? `<ul>${emerging
              .map(
                (t) =>
                  `<li>${escapeHtml(
                    [...labelList(t.label_phrases), ...labelList(t.label_terms)]
                      .slice(0, 5)
                      .join(", ") || `cluster ${t.cluster_id}`
                  )} (${t.size ?? t.post_ids?.length ?? "?" } posts)</li>`
              )
              .join("")}</ul>`
          : "<p>No emerging themes flagged.</p>"
      }${moreNote(totals.emerging_themes, emerging.length)}</section>

      ${
        meta.posts_truncated
          ? `<p class="chart-caption provenance-warn">Dupes/CIB scan all ${meta.posts_total_db} DB posts; fuzzy/sentiment use the ${meta.posts_in_snapshot}-post snapshot cohort.</p>`
          : ""
      }
    </article>
  `;
}

function moreNote(total: number | undefined, shown: number): string {
  if (!total || total <= shown) return "";
  return `<p class="brief-more-note">${total - shown} more in database — open Desk for full lists.</p>`;
}

function renderActorList(actors: CrossPollinationActor[], withSilos = false): string {
  if (!actors.length) return "<p>None flagged.</p>";
  return actors
    .map((a) => {
      const silos = withSilos
        ? ` · ${a.narratives.map((n) => n.narrative_name).slice(0, 3).join(", ")}`
        : "";
      return `<p class="brief-cluster"><strong>${escapeHtml(a.author_handle ?? a.author_id)}</strong> · ${a.narrative_count} narratives · score ${a.pollination_score.toFixed(2)}${escapeHtml(silos)}</p>`;
    })
    .join("");
}

function buildBriefMarkdown(
  narrative: NarrativeSummary,
  posts: Post[],
  cib: CibReport,
  exact: DuplicateCluster[],
  burst: DuplicateCluster[],
  fuzzy: CrossAuthorFuzzyCluster[],
  crossPollination: CrossPollinationReport | null,
  emerging: Array<{ label_terms?: string[]; label_phrases?: string[]; emerging_theme?: boolean; size?: number; cluster_id?: number }>
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
      const terms =
        [...labelList(t.label_phrases), ...labelList(t.label_terms)].slice(0, 5).join(", ") ||
        `cluster ${"cluster_id" in t ? t.cluster_id : "?"}`;
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

function bindBriefDownload(brief: NarrativeBrief): void {
  const link = document.getElementById("brief-download-md") as HTMLAnchorElement | null;
  if (!link || !brief.markdown) return;
  const slug = brief.meta.narrative_name.replace(/[^a-zA-Z0-9._-]+/g, "-").toLowerCase();
  const blob = new Blob([brief.markdown], { type: "text/markdown;charset=utf-8" });
  link.href = URL.createObjectURL(blob);
  link.download = `${slug || "brief"}.md`;
  link.hidden = false;
}

export function bindBriefPrint(): void {
  document.getElementById("brief-print")?.addEventListener("click", () => {
    window.print();
  });
}

export function resetBriefClipboardBinding(): void {
  briefClipboard.bound = false;
}

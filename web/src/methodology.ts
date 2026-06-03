import { DATA_LINKS } from "./api";

export function renderMethodology(): string {
  return `
    <article class="methodology prose">
      <section>
        <h2>What Heimdall measures</h2>
        <p>
          Heimdall tracks public social text around polarizing narratives, scores
          <strong>outrage escalation</strong>, and maps author-level propagation to flag
          possible <strong>coordinated inauthentic amplification (CIB)</strong>. Scores are
          heuristic research signals, not ground truth about intent or bot status.
        </p>
      </section>

      <section>
        <h2>Harmful content</h2>
        <p>
          Ingested posts may include hate speech or other upsetting language. The header notice
          states that material is shown to expose patterns and support counter-narrative work, not
          to amplify hateful views, and that it does not reflect the maintainer’s personal beliefs.
        </p>
      </section>

      <section>
        <h2>Data on this site</h2>
        <p>
          This dashboard reads a frozen export committed to the repo, not a live API.
          Scheduled ingest (GitHub Actions) appends to
          <a href="${DATA_LINKS.database}" target="_blank" rel="noopener">data/dashboard/heimdall.db</a>,
          then exports
          <a href="${DATA_LINKS.snapshot}" target="_blank" rel="noopener">snapshot.json</a>
          for Pages. The timestamp in the header is <code>generated_at</code> from that export.
        </p>
        <p class="sub">
          Post counts in the narrative dropdown reflect all posts in the database; charts and sentiment use up to
          250 most recent posts per narrative in the snapshot. Text coordination scans the full narrative in the DB.
        </p>
      </section>

      <section>
        <h2>Ingestion</h2>
        <ul>
          <li>Keywords define a <em>narrative</em>; each ingest pulls posts from configured platforms (e.g. X search timelines).</li>
          <li>Text is normalized; duplicate external IDs are upserted per narrative.</li>
          <li>Interactions (retweets, replies, etc.) become directed edges between authors when targets resolve.</li>
        </ul>
        <h3>X / Twitter guardrails (scheduled CI)</h3>
        <p>
          GitHub Actions runs ingest <strong>30 times per 24 hours</strong> (every 48 minutes UTC), rotating
          one keyword per run so the daily GraphQL budget is spread evenly.
        </p>
        <p>Automated ingest enforces conservative limits to reduce account risk:</p>
        <table class="method-table">
          <thead><tr><th>Limit</th><th>Default</th></tr></thead>
          <tbody>
            <tr><td>Keywords per ingest</td><td>5 max</td></tr>
            <tr><td>Posts stored per ingest</td><td>80 max</td></tr>
            <tr><td>Tweets per search</td><td>20 max</td></tr>
            <tr><td>Pause between searches</td><td>3 seconds</td></tr>
            <tr><td>GraphQL requests per day</td><td>30 (tracked in <code>x_rate_state.json</code>)</td></tr>
          </tbody>
        </table>
      </section>

      <section>
        <h2>Emerging themes (embeddings)</h2>
        <p>
          With <code>USE_EMBEDDING_THEMES=true</code> and <code>pip install -e ".[ml]"</code>, posts are
          vectorized with <code>all-MiniLM-L6-v2</code> and clustered (DBSCAN, with KMeans fallback).
          Cohesive clusters with low lexicon overlap are flagged as <strong>emerging themes</strong>
          (slang, typos, localized dog whistles) and receive a small outrage-index boost on rescore/ingest.
        </p>
        <p class="sub">
          API: <code>GET /api/v1/narratives/&#123;id&#125;/themes</code>.
          Labels use PMI-ranked phrases with filler filtering (multi-word frames like “red wave” stay intact).
          Fin-twit and crypto ticker posts are filtered out of clustering by default; the dashboard hides them unless you toggle “market chatter”.
          Select a cluster row to inspect sample text, escalation mix, and filter posts.
        </p>
      </section>

      <section>
        <h2>Outrage index</h2>
        <p>
          Each post gets an <strong>outrage index</strong> in [0, 1] from a lexicon pipeline
          (<code>heimdall-lexicon-v2.4</code>, optional <code>+embed-cluster</code> or
          <code>+twitter-roberta</code>): dehumanizing language,
          anti-authority framing,
          ragebait markers, conflict terms, negative sentiment, and stance polarization. Affection
          and neutral phrasing pull the score down.
        </p>
        <p>
          <strong>Mean outrage</strong> and the histogram summarize scored posts in the snapshot.
          <strong>Sentiment shift</strong> uses a dual-axis chart (Chart.js): a line for daily mean outrage
          (left axis) and bars for post volume per day (right axis), so a single angry post cannot look
          like a mass radicalization event. The trend label uses rolling-mean linear regression (≥3 days).
        </p>
      </section>

      <section>
        <h2>Duplicate text (amplification)</h2>
        <p>
          Posts are grouped by normalized text (lowercased, whitespace collapsed). Clusters with
          at least two posts are shown; often copypasta or coordinated messaging. Each cluster also
          measures inter-arrival timing: if five or more distinct authors post the same normalized
          text within a 90-second window, the cluster is flagged as a synchronized burst and CIB
          suspicion is raised (organic copypasta usually spreads over a long decay tail).
        </p>
      </section>

      <section>
        <h2>Dynamic diagnostic layer (<code>outrage-diagnostics.ts</code>)</h2>
        <p>
          Low-outrage or edge-free snapshots used to break chart layout (median dividers on
          <code>X = 0</code>, CRITICAL labels on the floor). A dedicated module now assesses each
          narrative before charts render.
        </p>
        <ul>
          <li>
            <strong>Baseline:</strong> <code>OUTRAGE_COMPRESSION_THRESHOLD = 0.15</code> — if max
            author outrage is at or below this, the lexicon read is treated as a Y-axis floor.
          </li>
          <li>
            <strong>Pipeline:</strong> <code>computeOutrageDiagnostics(posts, buckets)</code> returns
            compression flags, scored/unscored counts, and optional volume–outrage divergence
            (high post count + mean outrage &lt; 0.1 on a spike day).
          </li>
          <li>
            <strong>UX:</strong> <code>sentimentOutrageNoticeHtml</code> and
            <code>scatterOutrageFloorNoticeHtml</code> inject context on the Sentiment and
            Prioritization panels; the scatter chart skips degenerate median guides when spread is
            zero and links to the propagation network when edges are missing.
          </li>
        </ul>
      </section>

      <section>
        <h2>Adaptive axis re-scaling (<code>prioritization-scatter.ts</code>, <code>sentiment-chart.ts</code>)</h2>
        <p>
          Charts adapt to the threat material in each snapshot instead of forcing a 0–1 scale when
          data collapses on a wall or floor.
        </p>
        <h3>X-axis wall safety (scatter)</h3>
        <ul>
          <li>
            When <code>edges.length === 0</code>, spread is treated as absent
            (<code>hasPropagationSpread</code>).
          </li>
          <li>
            Median layout math no longer draws a vertical divider at <code>xMid = 0</code> on the
            Y-axis; <code>showVerticalQuadrant</code> requires real X variance and
            <code>xMid &gt; 0</code>.
          </li>
          <li>
            Fallbacks: pinned X scale headroom, on-canvas <strong>X = 0 wall</strong> overlay, and
            notices linking to the propagation panel.
          </li>
        </ul>
        <h3>Y-axis zoom (timeline + scatter)</h3>
        <ul>
          <li>
            If <code>computeOutrageDiagnostics</code> reports compression, axis max is recalculated
            (e.g. scatter <code>max(0.2, maxY + 0.04)</code>, timeline
            <code>max(0.2, peak mean + 0.05)</code>) so floor-clustered points are visible.
          </li>
          <li>
            Horizontal tier guides use <code>yPercentile75</code> instead of a median on the floor
            when outrage is compressed; labels move to a fixed upper band (<strong>TOP TIER</strong>
            / <strong>CRITICAL</strong>) so they are not dragged to the bottom-right.
          </li>
          <li>
            A dashed reference at <code>OUTRAGE_COMPRESSION_THRESHOLD</code> marks the lexicon floor
            on the scatter Y axis when zoomed.
          </li>
        </ul>
      </section>

      <section>
        <h2>Author prioritization scatter</h2>
        <p>
          Each author is plotted by out-degree (spread) vs max outrage. Points in the top-right
          quadrant are flagged as critical operational targets when both axes carry signal; on a
          lexicon floor or with no edges, the chart switches to relative tiers and on-canvas notices.
          IU astroturf registry matches are bright red. Click scatter points, timeline days, network
          nodes, or critical-target rows to filter the post list and focus the propagation graph on
          that author.
        </p>
      </section>

      <section>
        <h2>Propagation network (dashboard)</h2>
        <p>
          The Analysis tab renders author nodes and share/reply edges with vis-network. Node size
          reflects amplification out-degree; color reflects max outrage. A
          <strong>star topology</strong> (one hub with most out-edges) reads as coordinated;
          a <strong>distributed</strong> multi-hub shape reads more organic. Use the
          <strong>min edge weight</strong> slider to collapse single-share links and reduce hairballs;
          <strong>freeze layout</strong> stops physics after the graph settles.
        </p>
      </section>

      <section>
        <h2>CIB suspicion &amp; coordination</h2>
        <p>
          Heimdall separates <strong>text coordination</strong> (duplicate and fuzzy cross-author clusters,
          synchronized bursts) from <strong>graph coordination</strong> (propagation network topology). When the
          graph is sparse (&lt;10 edges or &lt;5% author coverage), graph scores are down-weighted and the UI
          warns analysts to rely on text signals instead of a misleading organic score of 1.0.
        </p>
        <p>
          Authors are nodes; share/reply edges link amplifiers to targets. NetworkX heuristics produce a
          <strong>graph suspicion score</strong>; text heuristics produce a <strong>text coordination score</strong>.
          The <strong>combined suspicion score</strong> merges both when the graph is sufficient; otherwise text
          dominates. <strong>Organic score</strong> is 1 − combined suspicion.
        </p>
        <ul>
          <li>One hub author accounting for &gt;50% of out-edges (graph)</li>
          <li>Graph density &gt; 0.15 with ≥5 authors (graph)</li>
          <li>Dense connected components (≥3 authors, high internal density) (graph)</li>
          <li>Cross-author fuzzy clusters (≥2 authors, Jaccard ≥ threshold) (text)</li>
          <li>Synchronized duplicate-text burst (≥5 authors, same normalized text within 90 seconds) (text)</li>
        </ul>
        <p>
          <strong>IU astroturf overlap</strong> (when present) counts narrative authors on platform
          <code>x</code> that appear in the Indiana University political-bot list (only comparable
          for Twitter/X author IDs, not Mastodon numeric IDs).
        </p>
      </section>

      <section>
        <h2>Limits &amp; ethics</h2>
        <ul>
          <li>Search-only X ingest may yield few or zero propagation edges; CIB can read as organic despite suspicious text.</li>
          <li>Lexicon outrage misses sarcasm and context; treat low scores as weak evidence, not innocence.</li>
          <li>Use only for public-data research; comply with platform terms and applicable law.</li>
        </ul>
        <p>
          Source code:
          <a href="https://github.com/saptreekly/Project-Heimdall" target="_blank" rel="noopener">github.com/saptreekly/Project-Heimdall</a>
        </p>
      </section>
    </article>
  `;
}

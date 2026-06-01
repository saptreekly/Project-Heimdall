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
          Post counts in the narrative dropdown reflect all posts in the database; charts use up to
          100 most recent posts per narrative in the snapshot.
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
          The analysis dashboard shows an <strong>Emerging themes timeline</strong> (horizontal token cards
          sorted by first activity date) so operators can spot shifting phrasing without exact-string matches.
          Click a cluster to filter posts in the investigation panel.
        </p>
      </section>

      <section>
        <h2>Outrage index</h2>
        <p>
          Each post gets an <strong>outrage index</strong> in [0, 1] from a lexicon pipeline
          (<code>heimdall-lexicon-v2.2</code>, optional <code>+embed-cluster</code>): dehumanizing language,
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
        <h2>Author prioritization scatter</h2>
        <p>
          Each author is plotted by out-degree (spread) vs max outrage. Points in the top-right
          quadrant are flagged as critical operational targets; IU astroturf registry matches are
          bright red. Click scatter points, timeline days, network nodes, or critical-target rows
          to filter the post list and focus the propagation graph on that author.
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
        <h2>CIB suspicion</h2>
        <p>
          Authors are nodes; share/reply edges link amplifiers to targets. NetworkX heuristics
          produce a <strong>suspicion score</strong> in [0, 1] and an <strong>organic score</strong>
          (1 − suspicion). Signals include:
        </p>
        <ul>
          <li>One hub author accounting for &gt;50% of out-edges</li>
          <li>Graph density &gt; 0.15 with ≥5 authors</li>
          <li>Dense connected components (≥3 authors, high internal density)</li>
          <li>High average outrage combined with other coordination signals</li>
          <li>Synchronized duplicate-text burst (≥5 authors, same normalized text within 90 seconds)</li>
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

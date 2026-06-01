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
        <h2>Outrage index</h2>
        <p>
          Each post gets an <strong>outrage index</strong> in [0, 1] from a lexicon pipeline
          (<code>heimdall-lexicon-v2.1</code>): dehumanizing language, anti-authority framing,
          ragebait markers, conflict terms, negative sentiment, and stance polarization. Affection
          and neutral phrasing pull the score down.
        </p>
        <p>
          <strong>Mean outrage</strong> and the histogram summarize scored posts in the snapshot.
          <strong>Sentiment shift</strong> buckets mean outrage by calendar day; the trend label compares
          first vs last bucket (escalating vs stable).
        </p>
      </section>

      <section>
        <h2>Duplicate text (amplification)</h2>
        <p>
          Posts are grouped by normalized text (lowercased, whitespace collapsed). Clusters with
          at least two posts are shown; often copypasta or coordinated messaging. Multiple authors
          in one cluster is a stronger coordination signal than a single author repeating a message.
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

import type { Post } from "./types";
import type { SentimentBucket } from "./sentiment-chart";

/** Authors/scores at or below this max read as lexicon-neutral (floor compression). */
export const OUTRAGE_COMPRESSION_THRESHOLD = 0.15;

export interface OutrageDiagnostics {
  compressed: boolean;
  maxAuthorOutrage: number;
  meanScoredOutrage: number;
  scoredCount: number;
  unscoredCount: number;
  volumeOutrageDivergence: {
    date: string;
    count: number;
    mean_outrage: number;
  } | null;
}

export function computeOutrageDiagnostics(
  posts: Post[],
  buckets: SentimentBucket[]
): OutrageDiagnostics {
  const scored = posts.filter((p) => p.outrage_index != null);
  const values = scored.map((p) => p.outrage_index as number);
  const maxAuthorOutrage =
    values.length > 0 ? Math.max(...values) : 0;
  const meanScoredOutrage =
    values.length > 0
      ? values.reduce((a, b) => a + b, 0) / values.length
      : 0;

  let volumeOutrageDivergence: OutrageDiagnostics["volumeOutrageDivergence"] =
    null;
  if (buckets.length > 0) {
    const counts = buckets.map((b) => b.count);
    const medianCount = median(counts);
    const spikeThreshold = Math.max(5, medianCount * 1.5);
    const spike = [...buckets].sort((a, b) => b.count - a.count)[0];
    if (
      spike &&
      spike.count >= spikeThreshold &&
      spike.mean_outrage < 0.1
    ) {
      volumeOutrageDivergence = {
        date: spike.date,
        count: spike.count,
        mean_outrage: spike.mean_outrage,
      };
    }
  }

  return {
    compressed: maxAuthorOutrage <= OUTRAGE_COMPRESSION_THRESHOLD,
    maxAuthorOutrage,
    meanScoredOutrage,
    scoredCount: scored.length,
    unscoredCount: posts.length - scored.length,
    volumeOutrageDivergence,
  };
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor(sorted.length * p))
  );
  return sorted[idx];
}

export function yPercentile75(points: { y: number }[]): number {
  return percentile(
    points.map((p) => p.y),
    0.75
  );
}

export function escapeDiagHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function sentimentOutrageNoticeHtml(diag: OutrageDiagnostics): string {
  if (!diag.compressed && !diag.volumeOutrageDivergence) return "";

  const spike = diag.volumeOutrageDivergence;
  const spikeLine = spike
    ? ` On <strong>${escapeDiagHtml(spike.date)}</strong> post volume peaked (${spike.count} posts) while mean outrage stayed near <strong>${spike.mean_outrage.toFixed(3)}</strong>.`
    : "";

  return `
    <div class="scatter-diagnosis chart-diagnosis-outrage" role="status">
      <p class="scatter-diagnosis-title">Volume without outrage (lexicon floor)</p>
      <p>
        Daily mean outrage flatlines near zero despite activity in the timeline.${spikeLine}
        Text in this narrative is scoring as civil/neutral under the static regex lexicon
        (<code>heimdall-lexicon-v2.4</code>), so author max outrage tops out around
        <strong>${diag.maxAuthorOutrage.toFixed(3)}</strong> (≤ ${OUTRAGE_COMPRESSION_THRESHOLD}).
      </p>
      <p class="scatter-diagnosis-sub">
        Check <a href="#priority-scatter-panel">Author prioritization</a> for the Y-axis floor.
        Coordinated copy may still appear in duplicate-text or embedding theme panels without high outrage scores.
      </p>
    </div>
  `;
}

export function scatterOutrageFloorNoticeHtml(diag: OutrageDiagnostics): string {
  if (!diag.compressed) return "";

  return `
    <div class="scatter-diagnosis chart-diagnosis-outrage" role="status">
      <p class="scatter-diagnosis-title">Y-axis floor (outrage ≤ ${OUTRAGE_COMPRESSION_THRESHOLD})</p>
      <p>
        Authors are compressed along the bottom of the chart: max outrage in this snapshot is
        <strong>${diag.maxAuthorOutrage.toFixed(3)}</strong> (mean scored
        ${diag.meanScoredOutrage.toFixed(3)} across ${diag.scoredCount} posts).
        That usually means ingest text is neutral/civil or phrasing missed by lexicon rules—not that volume is low.
      </p>
      <p class="scatter-diagnosis-sub">
        See <a href="#sentiment-chart-panel">Sentiment shift</a> for volume vs. mean-outrage divergence.
        ${diag.unscoredCount > 0 ? `${diag.unscoredCount} posts lack outrage scores.` : ""}
      </p>
    </div>
  `;
}

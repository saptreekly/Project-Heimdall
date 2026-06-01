import { DATA_LINKS, getSnapshotMeta } from "./api";
import { escapeHtml } from "./post-display";

export function renderDataAsOfHtml(generatedAt: string | null): string {
  if (!generatedAt) {
    return `<p class="data-as-of" id="data-as-of">Data as of: unknown</p>`;
  }
  return `<p class="data-as-of" id="data-as-of">Data as of <strong>${escapeHtml(generatedAt.slice(0, 19))} UTC</strong> · snapshot file only</p>`;
}

export function renderDataLinksExtra(): string {
  const meta = getSnapshotMeta();
  const ingest = meta?.ingest_workflow_url;
  const pages = meta?.pages_workflow_url;
  const parts = [
    `<a href="${DATA_LINKS.snapshot}" target="_blank" rel="noopener">snapshot.json</a>`,
    `<a href="${DATA_LINKS.database}" target="_blank" rel="noopener">heimdall.db</a>`,
    `<a href="${DATA_LINKS.publishDocs}" target="_blank" rel="noopener">how to update</a>`,
  ];
  if (ingest) {
    parts.push(
      `<a href="${escapeHtml(ingest)}" target="_blank" rel="noopener">ingest runs</a>`
    );
  }
  if (pages) {
    parts.push(
      `<a href="${escapeHtml(pages)}" target="_blank" rel="noopener">pages deploys</a>`
    );
  }
  return parts.join(" · ");
}

export function renderRateFooter(): string {
  const rate = getSnapshotMeta()?.x_rate;
  if (!rate) return "";
  const day = rate.date ?? "?";
  const count = rate.count ?? "?";
  return `<p class="rate-footer">X GraphQL today: <strong>${escapeHtml(String(count))}</strong> requests (${escapeHtml(String(day))})</p>`;
}

export function postsPanelCalloutHtml(): string {
  return `
    <p class="panel-callout">
      <strong>Reading posts:</strong> handle = account · tweet id = one status on X.
      <em>Exact</em> duplicate blocks need identical normalized text.
      <em>Cross-author fuzzy</em> clusters link spacing/typo variants across different accounts (Jaccard ≥ 0.82).
      Same-author loops are tagged separately.
    </p>
  `;
}

export function duplicatePanelTitle(): string {
  return "Exact duplicate text";
}

export function duplicatePanelCaption(): string {
  return `
    <p class="chart-caption dup-legend">
      Groups posts with <em>identical</em> normalized text (≥2). Click a cluster to filter the post list.
      <span class="dup-legend-warn">Orange</span> = copypasta ·
      <span class="dup-legend-threat">Red glow</span> = synchronized burst (≥5 authors / 90s).
      Post tags: same-author # · fuzzy × (cross-author) · copypasta %.
    </p>
  `;
}

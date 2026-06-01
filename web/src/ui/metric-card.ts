import { escapeHtml } from "../post-display";

export function metricCardHtml(
  label: string,
  value: string | number,
  sub?: string,
  wide = false
): string {
  const subHtml = sub ? `<div class="metric-sub">${escapeHtml(sub)}</div>` : "";
  return `<div class="metric-card${wide ? " metric-card-wide" : ""}">
    <span class="metric-label">${escapeHtml(label)}</span>
    <div class="metric-value">${escapeHtml(String(value))}</div>
    ${subHtml}
  </div>`;
}

export function metricsGridHtml(cards: string): string {
  return `<div class="metrics-grid">${cards}</div>`;
}

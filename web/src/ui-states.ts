import { escapeHtml } from "./post-display";

export function stateLoadingHtml(message = "Loading…"): string {
  return `<p class="state-loading" role="status">${escapeHtml(message)}</p>`;
}

export function stateEmptyHtml(message: string, hint?: string): string {
  const hintHtml = hint ? `<span class="state-hint">${escapeHtml(hint)}</span>` : "";
  return `<p class="state-empty">${escapeHtml(message)}${hintHtml}</p>`;
}

export function stateErrorHtml(title: string, message: string, hint?: string): string {
  const hintHtml = hint ? `<p class="state-hint">${escapeHtml(hint)}</p>` : "";
  return `<div class="state-error" role="alert">
    <strong>${escapeHtml(title)}</strong>
    <p>${escapeHtml(message)}</p>
    ${hintHtml}
  </div>`;
}

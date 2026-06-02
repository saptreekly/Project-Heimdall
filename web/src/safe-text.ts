/** Coerce snapshot/API values to display-safe strings. */
export function safeText(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

export function escapeHtml(value: unknown): string {
  return safeText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function labelList(values: unknown[] | undefined | null): string[] {
  if (!values?.length) return [];
  return values.map((v) => safeText(v).trim()).filter(Boolean);
}

import type {
  AmplificationReport,
  CibReport,
  DashboardSnapshot,
  NarrativeSummary,
  Post,
  SentimentShift,
} from "./types";

const STORAGE_KEY = "heimdall_api_base";

export const DEFAULT_API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() || "/api/v1";

let snapshotCache: DashboardSnapshot | null | undefined;

export function snapshotUrl(): string {
  return new URL("data/snapshot.json", import.meta.env.BASE_URL).href;
}

export function clearSnapshotCache(): void {
  snapshotCache = undefined;
}

export async function loadSnapshot(): Promise<DashboardSnapshot | null> {
  if (snapshotCache !== undefined) return snapshotCache;
  try {
    const res = await fetch(snapshotUrl());
    if (!res.ok) {
      snapshotCache = null;
      return null;
    }
    snapshotCache = (await res.json()) as DashboardSnapshot;
    return snapshotCache;
  } catch {
    snapshotCache = null;
    return null;
  }
}

export function isStaticMode(): boolean {
  return snapshotCache != null;
}

export function getSnapshotGeneratedAt(): string | null {
  return snapshotCache?.generated_at ?? null;
}

function normalizeBase(url: string): string {
  return url.trim().replace(/\/$/, "");
}

export function getApiBase(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored?.trim()) return normalizeBase(stored);
  } catch {
    /* private browsing */
  }
  return normalizeBase(DEFAULT_API_BASE);
}

export function setApiBase(url: string): void {
  const base = normalizeBase(url);
  try {
    localStorage.setItem(STORAGE_KEY, base);
  } catch {
    /* ignore */
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const base = getApiBase();
  const res = await fetch(`${base}${path}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function bundleFor(narrativeId: number) {
  return snapshotCache?.by_narrative_id[String(narrativeId)];
}

export async function listNarratives(): Promise<NarrativeSummary[]> {
  const snap = await loadSnapshot();
  if (snap?.narratives.length) return snap.narratives;
  return fetchJson("/narratives");
}

export async function fetchPosts(narrativeId: number, minOutrage = 0): Promise<Post[]> {
  const snap = await loadSnapshot();
  const posts = bundleFor(narrativeId)?.posts;
  if (posts) {
    if (minOutrage <= 0) return posts;
    return posts.filter((p) => (p.outrage_index ?? -1) >= minOutrage);
  }
  const q = minOutrage > 0 ? `?min_outrage=${minOutrage}` : "";
  return fetchJson(`/narratives/${narrativeId}/posts${q}`);
}

export async function fetchCib(narrativeId: number): Promise<CibReport> {
  const snap = await loadSnapshot();
  const cib = bundleFor(narrativeId)?.cib;
  if (cib) return cib;
  return fetchJson(`/narratives/${narrativeId}/cib`);
}

export async function fetchSentimentShift(narrativeId: number): Promise<SentimentShift> {
  const snap = await loadSnapshot();
  const sentiment = bundleFor(narrativeId)?.sentiment;
  if (sentiment) return sentiment;
  return fetchJson(`/narratives/${narrativeId}/sentiment-shift`);
}

export async function fetchAmplification(narrativeId: number): Promise<AmplificationReport> {
  const snap = await loadSnapshot();
  const amp = bundleFor(narrativeId)?.amplification;
  if (amp) return amp;
  return fetchJson(`/narratives/${narrativeId}/amplification`);
}

/**
 * Client-side Jaccard clustering — mirrors heimdall/analysis/near_duplicates.py
 * so analysts can change threshold without re-exporting the snapshot.
 */

import type {
  AuthorSpamSummary,
  CrossAuthorFuzzyCluster,
  NearDuplicateGroup,
  NearDuplicatesReport,
  Post,
} from "./types";

const WORD_RE = /[a-z0-9']+/g;
const SYNC_BURST_WINDOW_SECONDS = 90;
const SYNC_BURST_MIN_AUTHORS = 5;

export const JACCARD_THRESHOLD_DEFAULT = 0.82;
export const JACCARD_THRESHOLD_MIN = 0.55;
export const JACCARD_THRESHOLD_MAX = 0.98;
export const JACCARD_THRESHOLD_STEP = 0.01;
export const JACCARD_THRESHOLD_STORAGE_KEY = "heimdall-jaccard-threshold";

export function normalizeText(text: string, maxLen = 280): string {
  return (text || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLen);
}

export function tokenSet(text: string): Set<string> {
  const norm = normalizeText(text);
  const tokens = norm.match(WORD_RE);
  return new Set(tokens ?? []);
}

export function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const t of a) {
    if (b.has(t)) inter += 1;
  }
  const union = a.size + b.size - inter;
  return union === 0 ? 0 : inter / union;
}

type Row = [number, string, string, string];

function postsToRows(posts: Post[]): Row[] {
  return posts.map((p) => [p.id, p.author_id, p.text, p.posted_at]);
}

function unionFindClusters(
  n: number,
  pairs: Array<[number, number, number]>,
  minSize: number
): Array<[number[], number]> {
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (i: number): number => {
    let r = i;
    while (parent[r] !== r) {
      parent[r] = parent[parent[r]!]!;
      r = parent[r]!;
    }
    return r;
  };
  const union = (i: number, j: number) => {
    const ri = find(i);
    const rj = find(j);
    if (ri !== rj) parent[rj] = ri;
  };
  const edgeMax = new Map<string, number>();
  for (const [i, j, sim] of pairs) {
    union(i, j);
    const key = i < j ? `${i}:${j}` : `${j}:${i}`;
    edgeMax.set(key, Math.max(edgeMax.get(key) ?? 0, sim));
  }
  const buckets = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const r = find(i);
    if (!buckets.has(r)) buckets.set(r, []);
    buckets.get(r)!.push(i);
  }
  const out: Array<[number[], number]> = [];
  for (const indices of buckets.values()) {
    if (indices.length < minSize) continue;
    const sims: number[] = [];
    for (let a = 0; a < indices.length; a++) {
      for (let b = a + 1; b < indices.length; b++) {
        const i = indices[a]!;
        const j = indices[b]!;
        const key = i < j ? `${i}:${j}` : `${j}:${i}`;
        if (edgeMax.has(key)) sims.push(edgeMax.get(key)!);
      }
    }
    out.push([indices, sims.length ? Math.max(...sims) : 0]);
  }
  return out;
}

function pairwiseSimilarities(
  items: Array<[number, string, Set<string>]>,
  threshold: number,
  requireDistinctAuthors: boolean
): Array<[number, number, number]> {
  const pairs: Array<[number, number, number]> = [];
  for (let i = 0; i < items.length; i++) {
    const [, authorI, tokensI] = items[i]!;
    for (let j = i + 1; j < items.length; j++) {
      const [, authorJ, tokensJ] = items[j]!;
      if (requireDistinctAuthors && authorI === authorJ) continue;
      const sim = jaccardSimilarity(tokensI, tokensJ);
      if (sim >= threshold) pairs.push([i, j, sim]);
    }
  }
  return pairs;
}

function parseTime(iso: string): number | null {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

function maxDistinctAuthorsInWindow(
  events: Array<[number, string]>,
  windowSeconds: number
): number {
  if (!events.length) return 0;
  const ordered = [...events].sort((a, b) => a[0] - b[0]);
  let best = 0;
  let left = 0;
  const counts = new Map<string, number>();

  for (let right = 0; right < ordered.length; right++) {
    const [tRight, author] = ordered[right]!;
    counts.set(author, (counts.get(author) ?? 0) + 1);

    while (left <= right) {
      const [tLeft] = ordered[left]!;
      if ((tRight - tLeft) / 1000 <= windowSeconds) break;
      const aLeft = ordered[left]![1];
      const c = (counts.get(aLeft) ?? 1) - 1;
      if (c <= 0) counts.delete(aLeft);
      else counts.set(aLeft, c);
      left += 1;
    }
    best = Math.max(best, counts.size);
  }
  return best;
}

function clusterTimingMetrics(
  events: Array<[number, string]>
): Pick<
  CrossAuthorFuzzyCluster,
  | "burst_synchronized"
  | "burst_author_count"
  | "cluster_span_seconds"
  | "min_inter_arrival_seconds"
> {
  if (!events.length) {
    return {
      burst_synchronized: false,
      burst_author_count: 0,
      cluster_span_seconds: 0,
      min_inter_arrival_seconds: null,
    };
  }
  const times = events.map((e) => e[0]).sort((a, b) => a - b);
  const span =
    times.length > 1 ? (times[times.length - 1]! - times[0]!) / 1000 : 0;
  const deltas: number[] = [];
  for (let i = 1; i < times.length; i++) {
    deltas.push((times[i]! - times[i - 1]!) / 1000);
  }
  const burstAuthors = maxDistinctAuthorsInWindow(events, SYNC_BURST_WINDOW_SECONDS);
  return {
    burst_synchronized: burstAuthors >= SYNC_BURST_MIN_AUTHORS,
    burst_author_count: burstAuthors,
    cluster_span_seconds: Math.round(span * 100) / 100,
    min_inter_arrival_seconds: deltas.length ? Math.round(Math.min(...deltas) * 100) / 100 : null,
  };
}

function findNearDuplicateGroups(rows: Row[], threshold: number): NearDuplicateGroup[] {
  const byAuthor = new Map<string, [number, string, Set<string>][]>();
  for (const [pid, authorId, text] of rows) {
    const tokens = tokenSet(text);
    if (!tokens.size) continue;
    if (!byAuthor.has(authorId)) byAuthor.set(authorId, []);
    byAuthor.get(authorId)!.push([pid, text, tokens]);
  }

  const groups: NearDuplicateGroup[] = [];
  let groupId = 0;
  for (const [authorId, items] of byAuthor) {
    if (items.length < 2) continue;
    const indexed: Array<[number, string, Set<string>]> = items.map(([pid, text, tok]) => [
      pid,
      authorId,
      tok,
    ]);
    const pairs = pairwiseSimilarities(indexed, threshold, false);
    for (const [indices, maxSim] of unionFindClusters(items.length, pairs, 2)) {
      const postIds = indices.map((i) => items[i]![0]);
      const sample = indices
        .map((i) => items[i]![1])
        .sort((a, b) => b.length - a.length)[0]!;
      groups.push({
        group_id: groupId,
        author_id: authorId,
        post_ids: [...postIds].sort((a, b) => a - b),
        count: postIds.length,
        sample_text: sample.length > 240 ? `${sample.slice(0, 240)}…` : sample,
        max_similarity: Math.round(maxSim * 10000) / 10000,
      });
      groupId += 1;
    }
  }
  groups.sort((a, b) => b.count - a.count || b.max_similarity - a.max_similarity);
  return groups;
}

function findCrossAuthorFuzzyClusters(
  rows: Row[],
  threshold: number
): CrossAuthorFuzzyCluster[] {
  const items: Array<[number, string, string, Set<string>, string]> = [];
  for (const [pid, authorId, text, postedAt] of rows) {
    const tokens = tokenSet(text);
    if (!tokens.size) continue;
    items.push([pid, authorId, text, tokens, postedAt]);
  }
  if (items.length < 2) return [];

  const indexed: Array<[number, string, Set<string>]> = items.map(
    ([pid, author, , tokens]) => [pid, author, tokens]
  );
  const pairs = pairwiseSimilarities(indexed, threshold, true);
  const clusters: CrossAuthorFuzzyCluster[] = [];
  let clusterId = 0;

  for (const [indices, maxSim] of unionFindClusters(items.length, pairs, 2)) {
    const authorIds = [...new Set(indices.map((i) => items[i]![1]))].sort();
    if (authorIds.length < 2) continue;
    const postIds = indices.map((i) => items[i]![0]).sort((a, b) => a - b);
    const sample = indices
      .map((i) => items[i]![2])
      .sort((a, b) => b.length - a.length)[0]!;
    const events: Array<[number, string]> = [];
    for (const i of indices) {
      const t = parseTime(items[i]![4]);
      if (t != null) events.push([t, items[i]![1]]);
    }
    const timing = clusterTimingMetrics(events);
    clusters.push({
      cluster_id: clusterId,
      post_ids: postIds,
      author_ids: authorIds,
      author_count: authorIds.length,
      count: postIds.length,
      sample_text: sample.length > 240 ? `${sample.slice(0, 240)}…` : sample,
      max_similarity: Math.round(maxSim * 10000) / 10000,
      ...timing,
    });
    clusterId += 1;
  }

  clusters.sort((a, b) => {
    const burst = Number(b.burst_synchronized) - Number(a.burst_synchronized);
    if (burst) return burst;
    return (
      (b.burst_author_count ?? 0) - (a.burst_author_count ?? 0) ||
      b.author_count - a.author_count ||
      b.count - a.count ||
      b.max_similarity - a.max_similarity
    );
  });
  return clusters;
}

function authorSpamSummaries(
  rows: Row[],
  groups: NearDuplicateGroup[]
): AuthorSpamSummary[] {
  const byAuthor = new Map<string, Array<[number, string]>>();
  for (const [pid, authorId, , postedAt] of rows) {
    if (!byAuthor.has(authorId)) byAuthor.set(authorId, []);
    byAuthor.get(authorId)!.push([pid, postedAt]);
  }
  const nearByAuthor = new Map(
    groups.filter((g) => g.count >= 3).map((g) => [g.author_id, g])
  );
  const summaries: AuthorSpamSummary[] = [];
  for (const [authorId, posts] of byAuthor) {
    if (posts.length < 3) continue;
    const times = posts.map((p) => parseTime(p[1])).filter((t): t is number => t != null);
    let spanHours = 0;
    if (times.length >= 2) {
      spanHours = Math.round(((Math.max(...times) - Math.min(...times)) / 3600000) * 100) / 100;
    }
    const group = nearByAuthor.get(authorId);
    summaries.push({
      author_id: authorId,
      post_count: posts.length,
      post_ids: posts.map((p) => p[0]),
      span_hours: spanHours,
      near_duplicate_group_id: group?.group_id ?? null,
      near_duplicate_count: group?.count ?? 0,
    });
  }
  summaries.sort(
    (a, b) => b.post_count - a.post_count || b.near_duplicate_count - a.near_duplicate_count
  );
  return summaries;
}

export function resolveThresholdBounds(base: NearDuplicatesReport | null): {
  min: number;
  max: number;
  step: number;
  defaultThreshold: number;
} {
  return {
    min: base?.threshold_min ?? JACCARD_THRESHOLD_MIN,
    max: base?.threshold_max ?? JACCARD_THRESHOLD_MAX,
    step: base?.threshold_step ?? JACCARD_THRESHOLD_STEP,
    defaultThreshold: base?.default_threshold ?? base?.threshold ?? JACCARD_THRESHOLD_DEFAULT,
  };
}

export function loadStoredThreshold(defaultThreshold: number, min: number, max: number): number {
  const raw = localStorage.getItem(JACCARD_THRESHOLD_STORAGE_KEY);
  if (!raw) return defaultThreshold;
  const v = parseFloat(raw);
  if (!Number.isFinite(v)) return defaultThreshold;
  return Math.min(max, Math.max(min, v));
}

export function storeThreshold(value: number): void {
  localStorage.setItem(JACCARD_THRESHOLD_STORAGE_KEY, String(value));
}

export function recomputeNearDuplicatesReport(
  posts: Post[],
  threshold: number,
  base: NearDuplicatesReport | null
): NearDuplicatesReport {
  const rows = postsToRows(posts);
  const groups = findNearDuplicateGroups(rows, threshold);
  const crossFuzzy = findCrossAuthorFuzzyClusters(rows, threshold);
  const bounds = resolveThresholdBounds(base);

  return {
    threshold,
    default_threshold: bounds.defaultThreshold,
    threshold_min: bounds.min,
    threshold_max: bounds.max,
    threshold_step: bounds.step,
    threshold_live: true,
    same_author_group_count: groups.length,
    group_count: groups.length,
    groups,
    cross_author_fuzzy_count: crossFuzzy.length,
    cross_author_fuzzy: crossFuzzy,
    author_summaries: authorSpamSummaries(rows, groups),
  };
}

export function applyClusterTagsToPosts(
  posts: Post[],
  report: NearDuplicatesReport
): Post[] {
  const nearMap = new Map<number, number>();
  for (const g of report.groups) {
    for (const pid of g.post_ids) nearMap.set(pid, g.group_id);
  }
  const crossMap = new Map<number, number>();
  for (const c of report.cross_author_fuzzy ?? []) {
    for (const pid of c.post_ids) crossMap.set(pid, c.cluster_id);
  }
  return posts.map((p) => ({
    ...p,
    near_duplicate_group: nearMap.get(p.id) ?? null,
    cross_author_fuzzy_cluster: crossMap.get(p.id) ?? null,
  }));
}

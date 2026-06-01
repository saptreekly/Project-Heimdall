import type {
  AmplificationReport,
  CibReport,
  DashboardSnapshot,
  GraphAuthor,
  NarrativeSummary,
  Post,
  PropagationGraph,
  SentimentShift,
} from "./types";

const REPO_DATA_BASE =
  "https://github.com/saptreekly/Project-Heimdall/blob/main";

export const DATA_LINKS = {
  snapshot: `${REPO_DATA_BASE}/web/public/data/snapshot.json`,
  database: `${REPO_DATA_BASE}/data/dashboard/heimdall.db`,
  publishDocs: `${REPO_DATA_BASE}/data/dashboard/README.md`,
} as const;

let snapshotCache: DashboardSnapshot | null = null;

function snapshotCandidates(): string[] {
  const urls: string[] = [];
  const origin = window.location.origin;

  // Resolve relative to the deployed page (valid base; "/" alone throws in browsers)
  try {
    urls.push(new URL("data/snapshot.json", window.location.href).href);
  } catch {
    /* continue to fallbacks */
  }

  const viteBase = import.meta.env.BASE_URL || "/Project-Heimdall/";
  const pathBase = viteBase.startsWith("/") ? viteBase : `/${viteBase}`;
  urls.push(`${origin}${pathBase.replace(/\/?$/, "/")}data/snapshot.json`);
  urls.push(`${origin}/Project-Heimdall/data/snapshot.json`);

  return [...new Set(urls)];
}

export function clearSnapshotCache(): void {
  snapshotCache = null;
}

export async function loadSnapshot(): Promise<DashboardSnapshot> {
  if (snapshotCache) return snapshotCache;

  const tried: string[] = [];
  let lastStatus = "";

  for (const url of snapshotCandidates()) {
    tried.push(url);
    try {
      const res = await fetch(url);
      lastStatus = `${res.status} ${url}`;
      if (!res.ok) continue;
      snapshotCache = (await res.json()) as DashboardSnapshot;
      if (!snapshotCache.narratives?.length) {
        throw new Error("snapshot.json has no narratives");
      }
      return snapshotCache;
    } catch (e) {
      if (e instanceof Error && e.message.includes("no narratives")) throw e;
      lastStatus = e instanceof Error ? e.message : String(e);
    }
  }

  throw new Error(
    `Could not load data/snapshot.json (tried: ${tried.join(", ")}). Last: ${lastStatus}`
  );
}

export function getSnapshotGeneratedAt(): string | null {
  return snapshotCache?.generated_at ?? null;
}

function bundleFor(narrativeId: number) {
  const bundle = snapshotCache?.by_narrative_id[String(narrativeId)];
  if (!bundle) {
    throw new Error(`Narrative ${narrativeId} not found in snapshot`);
  }
  return bundle;
}

export async function listNarratives(): Promise<NarrativeSummary[]> {
  const snap = await loadSnapshot();
  return snap.narratives;
}

export async function fetchPosts(narrativeId: number, minOutrage = 0): Promise<Post[]> {
  await loadSnapshot();
  const posts = bundleFor(narrativeId).posts;
  if (minOutrage <= 0) return posts;
  return posts.filter((p) => (p.outrage_index ?? -1) >= minOutrage);
}

export async function fetchCib(narrativeId: number): Promise<CibReport> {
  await loadSnapshot();
  return bundleFor(narrativeId).cib;
}

export async function fetchSentimentShift(narrativeId: number): Promise<SentimentShift> {
  await loadSnapshot();
  return bundleFor(narrativeId).sentiment;
}

export async function fetchAmplification(narrativeId: number): Promise<AmplificationReport> {
  await loadSnapshot();
  return bundleFor(narrativeId).amplification;
}

function graphFromPosts(posts: Post[]): PropagationGraph {
  const authors = new Map<string, GraphAuthor>();
  for (const p of posts) {
    const existing = authors.get(p.author_id);
    const outrage = p.outrage_index ?? 0;
    if (!existing) {
      authors.set(p.author_id, {
        author_id: p.author_id,
        handle: null,
        max_outrage: outrage,
        post_count: 1,
      });
    } else {
      existing.post_count += 1;
      existing.max_outrage = Math.max(existing.max_outrage, outrage);
    }
  }
  return { authors: [...authors.values()], edges: [] };
}

export async function fetchPropagationGraph(narrativeId: number): Promise<PropagationGraph> {
  await loadSnapshot();
  const bundle = bundleFor(narrativeId);
  if (bundle.graph?.authors?.length) {
    return bundle.graph;
  }
  return graphFromPosts(bundle.posts);
}

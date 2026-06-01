import type {
  AmplificationReport,
  BenchmarkStats,
  CibReport,
  CrossPollinationReport,
  DashboardSnapshot,
  GraphAuthor,
  NarrativePollinationHits,
  NarrativeSummary,
  NearDuplicatesReport,
  Post,
  PropagationGraph,
  SentimentShift,
  SnapshotMeta,
  ThemesReport,
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

export async function loadSnapshot(options?: { bustCache?: boolean }): Promise<DashboardSnapshot> {
  if (snapshotCache && !options?.bustCache) return snapshotCache;
  snapshotCache = null;

  const tried: string[] = [];
  let lastStatus = "";
  const cacheBust = options?.bustCache ? `?v=${Date.now()}` : "";

  for (const url of snapshotCandidates()) {
    const fetchUrl = `${url}${cacheBust}`;
    tried.push(fetchUrl);
    try {
      const res = await fetch(fetchUrl, { cache: "no-store" });
      lastStatus = `${res.status} ${fetchUrl}`;
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

export function getSnapshotMeta(): SnapshotMeta | null {
  return snapshotCache?.meta ?? null;
}

export async function fetchNearDuplicates(narrativeId: number): Promise<NearDuplicatesReport | null> {
  await loadSnapshot();
  return bundleFor(narrativeId).near_duplicates ?? null;
}

export async function fetchBenchmark(narrativeId: number): Promise<BenchmarkStats | null> {
  await loadSnapshot();
  return bundleFor(narrativeId).benchmark ?? null;
}

export async function fetchCrossPollination(): Promise<CrossPollinationReport | null> {
  await loadSnapshot();
  return snapshotCache?.cross_pollination ?? null;
}

export async function fetchNarrativeCrossPollinationHits(
  narrativeId: number
): Promise<NarrativePollinationHits | null> {
  await loadSnapshot();
  return bundleFor(narrativeId).cross_pollination_hits ?? null;
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
        handle: p.author_handle ?? null,
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

const EMPTY_THEMES: ThemesReport = {
  available: false,
  reason: "Themes not included in this snapshot export.",
  narrative_id: 0,
  post_count: 0,
  cluster_count: 0,
  method: "none",
  model: "",
  clusters: [],
  timeline: [],
  emerging_theme_count: 0,
};

export async function fetchThemes(narrativeId: number): Promise<ThemesReport> {
  await loadSnapshot();
  const themes = bundleFor(narrativeId).themes;
  if (!themes) {
    return { ...EMPTY_THEMES, narrative_id: narrativeId };
  }
  return { ...EMPTY_THEMES, ...themes, narrative_id: narrativeId };
}

export async function fetchPropagationGraph(narrativeId: number): Promise<PropagationGraph> {
  await loadSnapshot();
  const bundle = bundleFor(narrativeId);
  if (bundle.graph?.authors?.length) {
    return bundle.graph;
  }
  return graphFromPosts(bundle.posts);
}

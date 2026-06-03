import type {
  AmplificationReport,
  CoordinationOverlay,
  CoordinationSubclusterRef,
  CrossAuthorFuzzyCluster,
  DuplicateCluster,
  NearDuplicateGroup,
  Post,
  ThemeCluster,
} from "./types";

export type CoordinationTier = "high" | "medium" | "low" | "context";

export interface CoordinationContext {
  amp: AmplificationReport | null;
  nearDup: {
    cross_author_fuzzy?: CrossAuthorFuzzyCluster[];
    groups?: NearDuplicateGroup[];
  } | null;
  posts: Post[];
  themes?: ThemeCluster[];
}

let activeContext: CoordinationContext | null = null;

export function setCoordinationContext(ctx: CoordinationContext): void {
  activeContext = ctx;
}

export function getCoordinationContext(): CoordinationContext | null {
  return activeContext;
}

function postIdSet(ids: number[]): Set<number> {
  return new Set(ids);
}

function overlapRefs(
  themeIds: Set<number>,
  clusters: Array<{ post_ids: number[]; count?: number; author_count?: number; author_ids?: string[]; burst_synchronized?: boolean; sample_text?: string }>,
  refPrefix: string
): CoordinationSubclusterRef[] {
  const refs: CoordinationSubclusterRef[] = [];
  clusters.forEach((cluster, index) => {
    const overlap = cluster.post_ids.filter((id) => themeIds.has(id));
    if (!overlap.length) return;
    refs.push({
      ref_id: `${refPrefix}_${index}`,
      overlap_count: overlap.length,
      cluster_count: cluster.count ?? cluster.post_ids.length,
      author_count: cluster.author_count ?? cluster.author_ids?.length ?? 0,
      burst_synchronized: Boolean(cluster.burst_synchronized),
      sample_text: (cluster.sample_text ?? "").slice(0, 160),
      post_ids: overlap,
    });
  });
  return refs.sort((a, b) => b.overlap_count - a.overlap_count || b.author_count - a.author_count);
}

export function computeThemeCoordination(
  postIds: number[],
  posts: Post[],
  cluster?: ThemeCluster | null
): CoordinationOverlay {
  if (cluster?.coordination) {
    return cluster.coordination;
  }

  const themeSet = postIdSet(postIds);
  const authors = new Set<string>();
  for (const pid of postIds) {
    const post = posts.find((p) => p.id === pid);
    if (post?.author_id) authors.add(post.author_id);
  }

  const ctx = activeContext;
  const exact = overlapRefs(themeSet, ctx?.amp?.clusters ?? [], "exact");
  const fuzzy = overlapRefs(themeSet, ctx?.nearDup?.cross_author_fuzzy ?? [], "fuzzy");
  const sameAuthor = overlapRefs(themeSet, ctx?.nearDup?.groups ?? [], "same_author");

  const emerging = Boolean(cluster?.emerging_theme);
  const tier = classifyTier({
    exact,
    fuzzy,
    uniqueAuthorCount: authors.size,
    uniquePostCount: postIds.length,
    emerging,
  });

  return {
    unique_author_count: authors.size,
    unique_post_count: postIds.length,
    exact_duplicate_clusters: exact,
    fuzzy_clusters: fuzzy,
    same_author_groups: sameAuthor,
    tier: tier.tier,
    tier_label: tier.label,
  };
}

export function classifyTier(input: {
  exact: CoordinationSubclusterRef[];
  fuzzy: CoordinationSubclusterRef[];
  uniqueAuthorCount: number;
  uniquePostCount: number;
  emerging: boolean;
}): { tier: CoordinationTier; label: string } {
  const hasBurstExact = input.exact.some(
    (ref) => ref.burst_synchronized && ref.author_count >= 3
  );
  const hasExactMulti = input.exact.some((ref) => ref.author_count >= 3);
  const hasFuzzyBurst = input.fuzzy.some((ref) => ref.burst_synchronized);
  const hasFuzzy = input.fuzzy.length > 0;

  if (hasBurstExact) return { tier: "high", label: "Template amplification" };
  if (hasExactMulti) return { tier: "high", label: "Exact duplicate campaign" };
  if (hasFuzzyBurst) return { tier: "medium", label: "Near-copy burst" };
  if (hasFuzzy) return { tier: "medium", label: "Near-copy campaign" };
  if (input.uniqueAuthorCount >= 3 && input.emerging) {
    return { tier: "medium", label: "Shared frame (emerging)" };
  }
  if (input.uniqueAuthorCount >= 2 && input.uniquePostCount >= 3) {
    return { tier: "medium", label: "Shared frame" };
  }
  if (input.uniquePostCount <= 2) return { tier: "context", label: "Context only" };
  return { tier: "low", label: "Distributed narrative" };
}

export function classifyDuplicateCluster(
  cluster: DuplicateCluster | CrossAuthorFuzzyCluster,
  kind: "exact" | "fuzzy"
): { tier: CoordinationTier; label: string } {
  const burst = Boolean(cluster.burst_synchronized);
  const authors = cluster.author_count ?? cluster.author_ids.length;
  if (kind === "exact") {
    if (burst && authors >= 3) return { tier: "high", label: "Template amplification" };
    if (authors >= 3) return { tier: "high", label: "Exact duplicate campaign" };
    return { tier: "medium", label: "Near-copy cluster" };
  }
  if (burst) return { tier: "medium", label: "Near-copy burst" };
  if (authors >= 3) return { tier: "medium", label: "Near-copy campaign" };
  return { tier: "low", label: "Fuzzy similarity" };
}

export function coordinationSummaryLine(overlay: CoordinationOverlay): string {
  const parts: string[] = [];
  parts.push(`${overlay.unique_post_count} unique posts`);
  parts.push(`${overlay.unique_author_count} authors`);
  if (overlay.exact_duplicate_clusters.length) {
    parts.push(`${overlay.exact_duplicate_clusters.length} exact dup subcluster${overlay.exact_duplicate_clusters.length === 1 ? "" : "s"}`);
  }
  if (overlay.fuzzy_clusters.length) {
    parts.push(`${overlay.fuzzy_clusters.length} fuzzy subcluster${overlay.fuzzy_clusters.length === 1 ? "" : "s"}`);
  }
  return parts.join(" · ");
}

export function findParentThemeLabel(
  postIds: number[],
  themes?: ThemeCluster[]
): string | null {
  const themeList = themes ?? activeContext?.themes ?? [];
  let best: { label: string; overlap: number } | null = null;
  const idSet = postIdSet(postIds);
  for (const theme of themeList) {
    const overlap = theme.post_ids.filter((id) => idSet.has(id)).length;
    if (overlap <= 0) continue;
    const label =
      theme.label_phrases?.[0] ??
      theme.label_terms?.[0] ??
      `cluster ${theme.cluster_id}`;
    if (!best || overlap > best.overlap) {
      best = { label, overlap };
    }
  }
  return best?.label ?? null;
}

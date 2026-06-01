import type { Post } from "./types";

export interface InvestigationFilter {
  authorId: string | null;
  date: string | null;
  postIds: number[] | null;
  label: string | null;
  hoursBack: number | null;
  burstOnly: boolean;
}

type FilterListener = (filter: InvestigationFilter) => void;

let allPosts: Post[] = [];
let filter: InvestigationFilter = {
  authorId: null,
  date: null,
  postIds: null,
  label: null,
  hoursBack: null,
  burstOnly: false,
};
const listeners = new Set<FilterListener>();

function postDateKey(postedAt: string): string {
  return postedAt.slice(0, 10);
}

function postAgeHours(postedAt: string): number {
  const t = Date.parse(postedAt);
  if (!Number.isFinite(t)) return Number.POSITIVE_INFINITY;
  return (Date.now() - t) / (1000 * 60 * 60);
}

export function setInvestigationPosts(posts: Post[]): void {
  allPosts = posts;
}

export function getInvestigationFilter(): InvestigationFilter {
  return { ...filter };
}

export function onInvestigationChange(listener: FilterListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  const snapshot = getInvestigationFilter();
  for (const listener of listeners) {
    listener(snapshot);
  }
}

export function selectAuthor(authorId: string, label?: string): void {
  filter = {
    ...filter,
    authorId,
    date: null,
    postIds: null,
    label: label ?? `Author ${authorId.slice(0, 12)}`,
    burstOnly: false,
  };
  notify();
}

export function selectDate(date: string): void {
  filter = {
    ...filter,
    authorId: null,
    date,
    postIds: null,
    label: `Date ${date}`,
    burstOnly: false,
  };
  notify();
}

export function selectThemeCluster(label: string, postIds: number[]): void {
  filter = {
    ...filter,
    authorId: null,
    date: null,
    postIds,
    label: `Theme: ${label}`,
    burstOnly: false,
  };
  notify();
}

export function selectDuplicateCluster(label: string, postIds: number[], burst: boolean): void {
  filter = {
    ...filter,
    authorId: null,
    date: null,
    postIds,
    label: burst ? `Burst: ${label}` : `Duplicate: ${label}`,
    burstOnly: burst,
  };
  notify();
}

export function setHoursBack(hours: number | null): void {
  filter = { ...filter, hoursBack: hours };
  notify();
}

export function clearInvestigationFilter(): void {
  if (
    !filter.authorId &&
    !filter.date &&
    !filter.postIds?.length &&
    !filter.hoursBack &&
    !filter.burstOnly
  ) {
    return;
  }
  filter = {
    authorId: null,
    date: null,
    postIds: null,
    label: null,
    hoursBack: null,
    burstOnly: false,
  };
  notify();
}

export function filterPosts(posts: Post[] = allPosts): Post[] {
  let out = posts;
  if (filter.authorId) {
    out = out.filter((p) => p.author_id === filter.authorId);
  }
  if (filter.date) {
    out = out.filter((p) => postDateKey(p.posted_at) === filter.date);
  }
  if (filter.postIds?.length) {
    const ids = new Set(filter.postIds);
    out = out.filter((p) => ids.has(p.id));
  }
  if (filter.hoursBack != null && filter.hoursBack > 0) {
    out = out.filter((p) => postAgeHours(p.posted_at) <= filter.hoursBack!);
  }
  return out;
}

export function hasActiveFilter(): boolean {
  return Boolean(
    filter.authorId ||
      filter.date ||
      filter.postIds?.length ||
      filter.hoursBack ||
      filter.burstOnly
  );
}

export function countMatchingPosts(posts: Post[] = allPosts): number {
  return filterPosts(posts).length;
}

export function countPostsForIds(postIds: number[], posts: Post[] = allPosts): number {
  if (!postIds.length) return 0;
  const ids = new Set(postIds);
  return posts.filter((p) => ids.has(p.id)).length;
}

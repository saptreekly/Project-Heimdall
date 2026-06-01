import type { Post } from "./types";

export interface InvestigationFilter {
  authorId: string | null;
  date: string | null;
  postIds: number[] | null;
  label: string | null;
}

type FilterListener = (filter: InvestigationFilter) => void;

let allPosts: Post[] = [];
let filter: InvestigationFilter = {
  authorId: null,
  date: null,
  postIds: null,
  label: null,
};
const listeners = new Set<FilterListener>();

function postDateKey(postedAt: string): string {
  return postedAt.slice(0, 10);
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
    authorId,
    date: null,
    postIds: null,
    label: label ?? `Author ${authorId.slice(0, 12)}`,
  };
  notify();
}

export function selectDate(date: string): void {
  filter = {
    authorId: null,
    date,
    postIds: null,
    label: `Date ${date}`,
  };
  notify();
}

export function selectThemeCluster(label: string, postIds: number[]): void {
  filter = {
    authorId: null,
    date: null,
    postIds,
    label: `Theme: ${label}`,
  };
  notify();
}

export function clearInvestigationFilter(): void {
  if (!filter.authorId && !filter.date && !filter.postIds?.length) return;
  filter = { authorId: null, date: null, postIds: null, label: null };
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
  return out;
}

export function hasActiveFilter(): boolean {
  return Boolean(filter.authorId || filter.date || filter.postIds?.length);
}

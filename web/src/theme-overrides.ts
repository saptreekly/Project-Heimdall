/** Analyst merge/split overrides for theme clusters (localStorage). */

import type { ThemeCluster } from "./types";

const STORAGE_KEY = "heimdall:theme-overrides";

export interface ThemeOverrideState {
  merges: Record<string, number[]>;
  splits: Record<string, number[][]>;
}

const EMPTY: ThemeOverrideState = { merges: {}, splits: {} };

function loadRaw(): ThemeOverrideState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as ThemeOverrideState;
    return {
      merges: parsed.merges ?? {},
      splits: parsed.splits ?? {},
    };
  } catch {
    return { ...EMPTY };
  }
}

function saveRaw(state: ThemeOverrideState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function narrativePrefix(narrativeId: number): string {
  return `${narrativeId}:`;
}

export function loadThemeOverrides(narrativeId: number): ThemeOverrideState {
  const all = loadRaw();
  const prefix = narrativePrefix(narrativeId);
  const merges: Record<string, number[]> = {};
  const splits: Record<string, number[][]> = {};
  for (const [key, ids] of Object.entries(all.merges)) {
    if (key.startsWith(prefix)) merges[key.slice(prefix.length)] = ids;
  }
  for (const [key, groups] of Object.entries(all.splits)) {
    if (key.startsWith(prefix)) splits[key.slice(prefix.length)] = groups;
  }
  return { merges, splits };
}

export function mergeThemeClusters(
  narrativeId: number,
  sourceIds: number[],
  targetId: number
): void {
  const all = loadRaw();
  const sorted = [...new Set(sourceIds)].sort((a, b) => a - b);
  const key = `${narrativePrefix(narrativeId)}${sorted.join("+")}->${targetId}`;
  all.merges[key] = sorted;
  saveRaw(all);
}

export function splitThemeCluster(
  narrativeId: number,
  clusterId: number,
  groups: number[][]
): void {
  const all = loadRaw();
  all.splits[`${narrativePrefix(narrativeId)}${clusterId}`] = groups;
  saveRaw(all);
}

function parseMergeTarget(mergeKey: string): number | null {
  const arrow = mergeKey.lastIndexOf("->");
  if (arrow < 0) return null;
  const targetId = parseInt(mergeKey.slice(arrow + 2), 10);
  return Number.isNaN(targetId) ? null : targetId;
}

export function applyThemeOverrides(
  clusters: ThemeCluster[],
  overrides: ThemeOverrideState
): ThemeCluster[] {
  let working = clusters.map((c) => ({ ...c, post_ids: [...c.post_ids] }));

  for (const [mergeKey, sourceIds] of Object.entries(overrides.merges)) {
    const targetId = parseMergeTarget(mergeKey);
    if (targetId === null) continue;
    const target = working.find((c) => c.cluster_id === targetId);
    if (!target) continue;
    for (const sourceId of sourceIds) {
      if (sourceId === targetId) continue;
      const source = working.find((c) => c.cluster_id === sourceId);
      if (!source) continue;
      target.post_ids = [...new Set([...target.post_ids, ...source.post_ids])];
      target.size = target.post_ids.length;
      working = working.filter((c) => c.cluster_id !== sourceId);
    }
  }

  for (const [clusterIdStr, groups] of Object.entries(overrides.splits)) {
    const clusterId = parseInt(clusterIdStr, 10);
    if (Number.isNaN(clusterId)) continue;
    const base = working.find((c) => c.cluster_id === clusterId);
    if (!base || groups.length < 2) continue;
    working = working.filter((c) => c.cluster_id !== clusterId);
    groups.forEach((postIds, idx) => {
      if (postIds.length === 0) return;
      working.push({
        ...base,
        cluster_id: clusterId * 100 + idx,
        post_ids: [...postIds],
        size: postIds.length,
      });
    });
  }

  return working;
}

export function clearThemeOverrides(): void {
  localStorage.removeItem(STORAGE_KEY);
}

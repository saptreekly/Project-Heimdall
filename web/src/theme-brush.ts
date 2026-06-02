/** Shared theme cluster selection for linked brushing across panels. */

export interface ThemeBrushState {
  clusterId: number | null;
  hoverClusterId: number | null;
  mergedClusterIds: number[] | null;
  postIds: number[] | null;
  label: string | null;
}

type BrushListener = (state: ThemeBrushState) => void;

let brush: ThemeBrushState = {
  clusterId: null,
  hoverClusterId: null,
  mergedClusterIds: null,
  postIds: null,
  label: null,
};

const listeners = new Set<BrushListener>();

export function getThemeBrush(): ThemeBrushState {
  return { ...brush };
}

export function onThemeBrushChange(listener: BrushListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  const snapshot = getThemeBrush();
  for (const listener of listeners) {
    listener(snapshot);
  }
}

export function setThemeBrushSelection(
  clusterId: number | null,
  postIds: number[] | null,
  label: string | null,
  mergedClusterIds: number[] | null = null
): void {
  brush = {
    ...brush,
    clusterId,
    mergedClusterIds,
    postIds,
    label,
    hoverClusterId: null,
  };
  notify();
}

export function setThemeBrushHover(clusterId: number | null): void {
  if (brush.hoverClusterId === clusterId) return;
  brush = { ...brush, hoverClusterId: clusterId };
  notify();
}

export function clearThemeBrush(): void {
  brush = {
    clusterId: null,
    hoverClusterId: null,
    mergedClusterIds: null,
    postIds: null,
    label: null,
  };
  notify();
}

/** Active highlight set: hover previews; click locks selection. */
export function activeBrushClusterIds(): number[] | null {
  const id = brush.clusterId ?? brush.hoverClusterId;
  if (id == null) return null;
  if (brush.mergedClusterIds?.length) return brush.mergedClusterIds;
  return [id];
}

export function isClusterDimmed(clusterId: number): boolean {
  const active = activeBrushClusterIds();
  if (!active) return false;
  return !active.includes(clusterId);
}

export function brushOpacity(clusterId: number): number {
  return isClusterDimmed(clusterId) ? 0.22 : 1;
}

import type { ClusterSimilarityEdge, ThemeMergeNode, ThemeTimelineEntry } from "./types";
import { escapeHtml, labelList, safeText } from "./safe-text";

export interface MergedThemeGroup {
  id: string;
  clusterIds: number[];
  label: string;
  postIds: number[];
  size: number;
  emerging: boolean;
}

export interface ThemeTimelineLike {
  cluster_id: number;
  label_terms?: string[];
  label_phrases?: string[];
  post_ids?: number[];
  size: number;
  emerging_theme: boolean;
  is_noise?: boolean;
}

function displayLabel(entry: ThemeTimelineLike): string {
  const phrases = labelList(entry.label_phrases);
  if (phrases.length > 0) return phrases[0];
  const terms = labelList(entry.label_terms);
  if (terms.length > 0) return terms[0];
  return `cluster ${entry.cluster_id}`;
}

function unionFindParent(parent: Map<number, number>, node: number): number {
  let root = node;
  while (parent.get(root) !== root) {
    root = parent.get(root)!;
  }
  let current = node;
  while (parent.get(current) !== root) {
    const next = parent.get(current)!;
    parent.set(current, root);
    current = next;
  }
  return root;
}

export function computeMergedGroups(
  timeline: ThemeTimelineLike[],
  similarity: ClusterSimilarityEdge[],
  threshold: number
): MergedThemeGroup[] {
  const leaves = timeline.filter((t) => !t.is_noise);
  if (leaves.length === 0) return [];

  const parent = new Map<number, number>();
  for (const entry of leaves) {
    parent.set(entry.cluster_id, entry.cluster_id);
  }

  for (const edge of similarity) {
    if (edge.similarity < threshold) continue;
    const rootA = unionFindParent(parent, edge.a);
    const rootB = unionFindParent(parent, edge.b);
    if (rootA !== rootB) {
      parent.set(rootB, rootA);
    }
  }

  const groups = new Map<number, ThemeTimelineLike[]>();
  for (const entry of leaves) {
    const root = unionFindParent(parent, entry.cluster_id);
    const bucket = groups.get(root) ?? [];
    bucket.push(entry);
    groups.set(root, bucket);
  }

  return [...groups.entries()]
    .map(([root, members]) => {
      const labels = members.map(displayLabel);
      const postIds = [...new Set(members.flatMap((m) => m.post_ids ?? []))];
      return {
        id: members.length === 1 ? `c${root}` : `m${root}`,
        clusterIds: members.map((m) => m.cluster_id),
        label: members.length === 1 ? labels[0] : labels.slice(0, 2).join(" + "),
        postIds,
        size: postIds.length,
        emerging: members.some((m) => m.emerging_theme),
      };
    })
    .sort((a, b) => b.size - a.size);
}

function mergeGroupsHtml(groups: MergedThemeGroup[]): string {
  return groups
    .map(
      (group) => `<button
        type="button"
        class="theme-merge-group${group.emerging ? " theme-merge-group-emerging" : ""}${group.clusterIds.length > 1 ? " theme-merge-group-merged" : ""}"
        data-group-id="${escapeHtml(group.id)}"
      >
        <span class="theme-merge-group-label">${escapeHtml(group.label)}</span>
        <span class="theme-merge-group-meta">${group.size} posts · ${group.clusterIds.length} cluster${group.clusterIds.length === 1 ? "" : "s"}</span>
      </button>`
    )
    .join("");
}

function bindMergeGroupClicks(
  host: HTMLElement,
  groups: MergedThemeGroup[],
  onSelectGroup: (group: MergedThemeGroup) => void
): void {
  host.querySelectorAll<HTMLButtonElement>(".theme-merge-group").forEach((btn, idx) => {
    btn.addEventListener("click", () => {
      host.querySelectorAll(".theme-merge-group").forEach((el) => el.classList.remove("theme-merge-group-active"));
      btn.classList.add("theme-merge-group-active");
      onSelectGroup(groups[idx]);
    });
  });
}

/** Mount merge explorer once; slider updates groups without rebuilding the whole panel. */
export function updateMergeExplorer(
  host: HTMLElement,
  similarity: ClusterSimilarityEdge[],
  mergeCandidates: ClusterSimilarityEdge[],
  timeline: ThemeTimelineEntry[],
  threshold: number,
  onThresholdChange: (value: number) => void,
  onSelectGroup: (group: MergedThemeGroup) => void
): void {
  const groups = computeMergedGroups(timeline, similarity, threshold);
  const maxSim = similarity[0]?.similarity ?? MERGE_DEFAULT_MAX;
  const minSim = similarity[similarity.length - 1]?.similarity ?? MERGE_DEFAULT_MIN;

  if (!host.dataset.mounted) {
    host.dataset.mounted = "1";
    host.innerHTML = `
      <div class="theme-merge-panel">
        <div class="theme-merge-controls">
          <label class="theme-merge-label" for="theme-merge-threshold">
            Merge threshold
            <span class="theme-merge-value" id="theme-merge-value">${threshold.toFixed(2)}</span>
          </label>
          <input
            id="theme-merge-threshold"
            class="theme-merge-slider"
            type="range"
            min="${minSim.toFixed(2)}"
            max="${Math.max(maxSim, 0.95).toFixed(2)}"
            step="0.01"
            value="${threshold.toFixed(2)}"
          />
          <p class="chart-caption theme-merge-hint">
            Drag right to merge more clusters. Auto-merge at export uses ${AUTO_MERGE_SIM.toFixed(2)} cosine similarity.
          </p>
        </div>
        <div id="theme-merge-candidates-host">${
          mergeCandidates.length
            ? `<ul class="theme-merge-candidates">${mergeCandidates
                .slice(0, 4)
                .map(
                  (edge) =>
                    `<li><code>${edge.a}</code> ↔ <code>${edge.b}</code> · ${(edge.similarity * 100).toFixed(0)}% similar</li>`
                )
                .join("")}</ul>`
            : ""
        }</div>
        <div class="theme-merge-groups" id="theme-merge-groups-host">${mergeGroupsHtml(groups)}</div>
      </div>
    `;

    const slider = host.querySelector<HTMLInputElement>("#theme-merge-threshold");
    const valueEl = host.querySelector("#theme-merge-value");
    let sliderTimer: number | undefined;
    slider?.addEventListener("input", () => {
      const value = parseFloat(slider.value);
      if (valueEl) valueEl.textContent = value.toFixed(2);
      window.clearTimeout(sliderTimer);
      sliderTimer = window.setTimeout(() => {
        onThresholdChange(value);
        const nextGroups = computeMergedGroups(timeline, similarity, value);
        const groupsHost = host.querySelector("#theme-merge-groups-host");
        if (groupsHost) {
          groupsHost.innerHTML = mergeGroupsHtml(nextGroups);
          bindMergeGroupClicks(host, nextGroups, onSelectGroup);
        }
      }, 120);
    });

    bindMergeGroupClicks(host, groups, onSelectGroup);
    return;
  }

  const valueEl = host.querySelector("#theme-merge-value");
  const slider = host.querySelector<HTMLInputElement>("#theme-merge-threshold");
  if (valueEl) valueEl.textContent = threshold.toFixed(2);
  if (slider) slider.value = threshold.toFixed(2);

  const groupsHost = host.querySelector("#theme-merge-groups-host");
  if (groupsHost) {
    groupsHost.innerHTML = mergeGroupsHtml(groups);
    bindMergeGroupClicks(host, groups, onSelectGroup);
  }
}

export function renderMergeDendrogram(host: HTMLElement, mergeTree: ThemeMergeNode[]): void {
  if (!mergeTree.length) {
    host.innerHTML = "";
    return;
  }

  const leaves = mergeTree.filter((n) => n.leaf);
  const internals = mergeTree.filter((n) => !n.leaf).sort((a, b) => (a.similarity ?? 0) - (b.similarity ?? 0));

  host.innerHTML = `
    <div class="theme-dendrogram">
      <div class="theme-dendrogram-leaves">${leaves
        .map(
          (node) =>
            `<span class="theme-dendrogram-leaf" data-cluster-id="${node.cluster_id ?? ""}" title="${escapeHtml(safeText(node.label))}">${escapeHtml(safeText(node.label))}</span>`
        )
        .join("")}</div>
      <div class="theme-dendrogram-merges">${internals
        .map(
          (node) =>
            `<div class="theme-dendrogram-merge" style="--merge-sim:${((node.similarity ?? 0) * 100).toFixed(0)}">
              <span class="theme-dendrogram-merge-bar"></span>
              <span class="theme-dendrogram-merge-label">${escapeHtml(safeText(node.label))} <em>${((node.similarity ?? 0) * 100).toFixed(0)}%</em></span>
            </div>`
        )
        .join("")}</div>
    </div>
  `;
}

export const MERGE_DEFAULT_MIN = 0.72;
export const MERGE_DEFAULT_MAX = 0.86;
export const AUTO_MERGE_SIM = 0.87;

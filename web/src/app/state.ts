import type { DeskMode } from "../desk-modes";
import { deskModeFromUrl } from "../desk-modes";
import type { AppTab } from "../tabs";
import { tabFromUrl } from "../tabs";
import type {
  AmplificationReport,
  CibReport,
  DuplicateCluster,
  NarrativeBrief,
  NarrativeSummary,
  NearDuplicatesReport,
  Post,
  ThemesReport,
} from "../types";

export const BLUR_SENSITIVE_KEY = "heimdall-blur-sensitive";
export const COMPACT_CHARTS_KEY = "heimdall-compact-charts";
export const POST_LIST_INITIAL = 20;
export const POST_LIST_MAX = 50;

export type ChartMountFns = {
  mountPulse: () => void;
  mountFrames: () => void;
  mountNetwork: () => void;
};

export const appState = {
  currentTab: tabFromUrl() as AppTab,
  currentDeskMode: deskModeFromUrl() as DeskMode,
  lastLoadedPosts: [] as Post[],
  lastGraphEdgeCount: 0,
  blurSensitive: localStorage.getItem(BLUR_SENSITIVE_KEY) === "1",
  compactCharts: localStorage.getItem(COMPACT_CHARTS_KEY) !== "0",
  groupAuthorPosts: true,
  postListLimit: POST_LIST_INITIAL,
  lastNearDup: null as NearDuplicatesReport | null,
  lastAmpClusters: [] as DuplicateCluster[],
  lastThemesReport: null as ThemesReport | null,
  clusterSourcePosts: [] as Post[],
  jaccardThreshold: 0.82,
  totalNarrativePosts: 0,
  lastCriticalCount: 0,
  lastAnomalyCount: 0,
  briefContext: null as {
    narrative: NarrativeSummary;
    posts: Post[];
    cib: CibReport;
    amp: AmplificationReport;
    themes: ThemesReport;
    crossPollination: import("../types").CrossPollinationReport | null;
    brief: NarrativeBrief | null;
  } | null,
  chartMountFns: null as ChartMountFns | null,
  chartsMounted: {
    pulse: false,
    frames: false,
    network: false,
  },
};

export const rootEl = document.getElementById("app");
if (!rootEl) throw new Error("#app missing");
export const root: HTMLElement = rootEl;

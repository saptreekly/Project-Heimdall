export interface NarrativeSummary {
  id: number;
  name: string;
  keywords: string;
  post_count: number;
}

export interface Post {
  id: number;
  platform: string;
  external_id?: string | null;
  author_id: string;
  author_handle?: string | null;
  text: string;
  posted_at: string;
  outrage_index: number | null;
  sentiment_label: string | null;
  polarity?: string | null;
  escalation_tier?: string | null;
  negativity_score?: number | null;
  ragebait_score?: number | null;
  stance_score?: number | null;
  dehumanization_score?: number | null;
  anti_authority_score?: number | null;
  conflict_escalation?: number | null;
  benchmark_label: string | null;
  near_duplicate_group?: number | null;
  cross_author_fuzzy_cluster?: number | null;
  copypasta_score?: number | null;
  status_url?: string | null;
}

export interface CrossAuthorFuzzyCluster {
  cluster_id: number;
  post_ids: number[];
  author_ids: string[];
  author_count: number;
  count: number;
  sample_text: string;
  max_similarity: number;
  burst_synchronized?: boolean;
  burst_author_count?: number;
  cluster_span_seconds?: number;
  min_inter_arrival_seconds?: number | null;
}

export interface NearDuplicateGroup {
  group_id: number;
  author_id: string;
  post_ids: number[];
  count: number;
  sample_text: string;
  max_similarity: number;
}

export interface AuthorSpamSummary {
  author_id: string;
  post_count: number;
  post_ids: number[];
  span_hours: number;
  near_duplicate_group_id: number | null;
  near_duplicate_count: number;
}

export interface NearDuplicatesReport {
  threshold: number;
  default_threshold?: number;
  threshold_min?: number;
  threshold_max?: number;
  threshold_step?: number;
  /** Recomputed in-browser when the analyst moves the slider. */
  threshold_live?: boolean;
  same_author_group_count?: number;
  group_count: number;
  groups: NearDuplicateGroup[];
  cross_author_fuzzy_count?: number;
  cross_author_fuzzy?: CrossAuthorFuzzyCluster[];
  author_summaries: AuthorSpamSummary[];
}

export interface BenchmarkStats {
  labeled_posts: number;
  total_posts: number;
  labels: string[];
}

export interface SnapshotMeta {
  ingest_workflow_url?: string;
  pages_workflow_url?: string;
  x_rate?: { date?: string; count?: number } | null;
}

export interface CrossPollinationNarrativeRef {
  narrative_id: number;
  narrative_name: string;
  post_count: number;
  max_outrage: number | null;
  first_seen: string | null;
  last_seen: string | null;
}

export interface CrossPollinationActor {
  actor_key: string;
  platform: string;
  author_id: string;
  author_handle: string | null;
  narrative_count: number;
  total_posts: number;
  pollination_score: number;
  span_days: number;
  narratives: CrossPollinationNarrativeRef[];
  other_narratives?: CrossPollinationNarrativeRef[];
  other_narrative_count?: number;
}

export interface NarrativePairOverlap {
  narrative_a_id: number;
  narrative_a_name: string;
  narrative_b_id: number;
  narrative_b_name: string;
  shared_actor_count: number;
}

export interface CrossPollinationReport {
  available: boolean;
  min_narratives?: number;
  actor_count: number;
  narrative_count?: number;
  actors: CrossPollinationActor[];
  narrative_pairs?: NarrativePairOverlap[];
}

export interface NarrativePollinationHits {
  narrative_id: number;
  hit_count: number;
  actors: CrossPollinationActor[];
}

export interface CibReport {
  narrative_id: number;
  suspicion_score: number;
  organic_score: number;
  graph_suspicion_score: number;
  text_coordination_score: number;
  graph_sufficient: boolean;
  graph_coverage_pct: number;
  signals: string[];
  graph_signals?: string[];
  text_signals?: string[];
  node_count: number;
  edge_count: number;
  density: number;
  top_amplifiers: Array<{
    author_id: string;
    out_degree: number;
    in_degree: number;
    max_outrage: number;
  }>;
  coordinated_clusters: unknown[];
  iu_astroturf: {
    authors_in_narrative: number;
    known_political_bots: number;
    known_bot_ratio: number;
    labeled_accounts: unknown[];
    note: string | null;
  } | null;
}

export interface NarrativeProvenance {
  posts_total_db: number;
  posts_in_snapshot: number;
  snapshot_post_limit: number;
  posts_truncated: boolean;
  analysis_scope: string;
  sentiment_scope: string;
  text_coordination_scope: string;
  outrage_model_version: string;
  duplicate_cluster_count: number;
  fuzzy_cluster_count: number;
  coordination_signal_count?: number;
  posts_per_author?: number | null;
  distinct_theme_count?: number;
  theme_cluster_count?: number;
  graph_edge_count: number;
  graph_author_count: number;
  graph_connected_author_count: number;
  graph_coverage_pct: number;
  graph_sufficient: boolean;
  theme_model: string;
  theme_method: string;
  theme_model_reliable: boolean;
  outrage_scored_count: number;
  outrage_max: number | null;
  outrage_mean: number | null;
  outrage_compressed: boolean;
}

export interface SentimentShift {
  narrative_id: number;
  buckets: Array<{
    date: string;
    mean_outrage: number;
    count: number;
    mean_negativity?: number;
    mean_ragebait?: number;
    mean_stance?: number;
    mean_dehumanization?: number;
    mean_anti_authority?: number;
    tier_counts?: Record<string, number>;
    polarity_counts?: Record<string, number>;
    volume_outrage_divergence?: boolean;
  }>;
  trend: string;
  divergence_days?: Array<{ date: string; count: number; mean_outrage: number }>;
  week_over_week?: {
    available: boolean;
    reason?: string;
    recent_week_mean_outrage?: number;
    prior_week_mean_outrage?: number;
    mean_outrage_delta?: number;
    recent_week_posts?: number;
    prior_week_posts?: number;
    volume_delta_pct?: number;
    alert?: string | null;
  };
}

export interface DuplicateCluster {
  count: number;
  author_count: number;
  author_ids: string[];
  post_ids: number[];
  sample_text: string;
  burst_synchronized?: boolean;
  burst_author_count?: number;
  cluster_span_seconds?: number;
  min_inter_arrival_seconds?: number | null;
}

export interface AmplificationReport {
  narrative_id: number;
  cluster_count: number;
  clusters: DuplicateCluster[];
}

export interface GraphAuthor {
  author_id: string;
  handle: string | null;
  max_outrage: number;
  post_count: number;
  known_bot?: boolean;
  bot_label?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  source_post_id?: number;
  target_post_id?: number | null;
  occurred_at?: string | null;
}

export interface GraphInteractionStats {
  edge_count: number;
  author_count: number;
  connected_author_count: number;
  isolated_author_count: number;
  by_type: Record<string, number>;
}

export interface PropagationGraph {
  authors: GraphAuthor[];
  edges: GraphEdge[];
  stats?: GraphInteractionStats;
}

export interface ThemeCluster {
  cluster_id: number;
  post_ids: number[];
  size: number;
  cohesion: number;
  lexicon_hit_rate: number;
  emerging_theme: boolean;
  label_terms: string[];
  label_phrases?: string[];
  label_distinctiveness?: number;
  sample_text: string;
  first_seen?: string | null;
  last_seen?: string | null;
  active_days?: number;
  daily_counts?: Record<string, number>;
  author_entropy?: number;
  quality_score?: number;
  confidence_tier?: "high" | "medium" | "low";
  is_noise?: boolean;
  is_market_chatter?: boolean;
  market_chatter_rate?: number;
  filter_reason?: string | null;
  map_x?: number | null;
  map_y?: number | null;
}

export interface ThemeClusterMapPoint {
  cluster_id: number;
  x: number;
  y: number;
  size: number;
  label: string;
  emerging_theme: boolean;
  is_noise?: boolean;
}

export interface ClusterSimilarityEdge {
  a: number;
  b: number;
  similarity: number;
}

export interface ThemeMergeNode {
  id: string;
  cluster_id: number | null;
  label: string;
  children: string[];
  similarity: number;
  size: number;
  leaf: boolean;
}

export interface ThemeTimelineEntry {
  cluster_id: number;
  label_terms: string[];
  label_phrases?: string[];
  label_distinctiveness?: number;
  emerging_theme: boolean;
  quality_score?: number;
  author_entropy?: number;
  is_noise?: boolean;
  is_market_chatter?: boolean;
  market_chatter_rate?: number;
  size: number;
  first_seen: string | null;
  last_seen: string | null;
  daily_counts?: Record<string, number>;
  post_ids: number[];
}

export interface ThemesReport {
  available: boolean;
  reason: string | null;
  narrative_id: number;
  post_count: number;
  cluster_count: number;
  method: string;
  model: string;
  clusters: ThemeCluster[];
  timeline?: ThemeTimelineEntry[];
  cluster_map?: ThemeClusterMapPoint[];
  cluster_similarity?: ClusterSimilarityEdge[];
  merge_candidates?: ClusterSimilarityEdge[];
  merge_tree?: ThemeMergeNode[];
  emerging_theme_count: number;
  market_chatter_count?: number;
  market_chatter_post_count?: number;
  distinct_theme_count?: number;
  filtered_post_count?: number;
  quality_metrics?: {
    silhouette?: number | null;
    davies_bouldin?: number | null;
    noise_ratio?: number;
    narrative_purity?: number | null;
    notes?: string[];
  };
  theme_lineage?: Array<{
    week: string;
    cluster_count: number;
    clusters: Array<{
      cluster_id: number;
      label: string;
      size: number;
      post_ids: number[];
      emerging_theme: boolean;
    }>;
    continues_from: Array<{ week: string; label: string; overlap: number }>;
  }>;
}

export interface NarrativeBundle {
  posts: Post[];
  cib: CibReport;
  sentiment: SentimentShift;
  amplification: AmplificationReport;
  near_duplicates?: NearDuplicatesReport;
  cross_pollination_hits?: NarrativePollinationHits;
  graph?: PropagationGraph;
  themes?: ThemesReport;
  benchmark?: BenchmarkStats | null;
  provenance?: NarrativeProvenance;
}

export interface DashboardSnapshot {
  version: number;
  generated_at: string;
  narratives: NarrativeSummary[];
  by_narrative_id: Record<string, NarrativeBundle>;
  cross_pollination?: CrossPollinationReport;
  meta?: SnapshotMeta;
}

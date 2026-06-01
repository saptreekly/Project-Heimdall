export interface NarrativeSummary {
  id: number;
  name: string;
  keywords: string;
  post_count: number;
}

export interface Post {
  id: number;
  platform: string;
  author_id: string;
  text: string;
  posted_at: string;
  outrage_index: number | null;
  sentiment_label: string | null;
  benchmark_label: string | null;
}

export interface CibReport {
  narrative_id: number;
  suspicion_score: number;
  organic_score: number;
  signals: string[];
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

export interface SentimentShift {
  narrative_id: number;
  buckets: Array<{ date: string; mean_outrage: number; count: number }>;
  trend: string;
}

export interface DuplicateCluster {
  count: number;
  author_count: number;
  author_ids: string[];
  post_ids: number[];
  sample_text: string;
}

export interface AmplificationReport {
  narrative_id: number;
  cluster_count: number;
  clusters: DuplicateCluster[];
}

export interface NarrativeBundle {
  posts: Post[];
  cib: CibReport;
  sentiment: SentimentShift;
  amplification: AmplificationReport;
}

export interface DashboardSnapshot {
  version: number;
  generated_at: string;
  narratives: NarrativeSummary[];
  by_narrative_id: Record<string, NarrativeBundle>;
}

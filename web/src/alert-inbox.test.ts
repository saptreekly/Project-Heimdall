import { describe, expect, it } from "vitest";
import { buildAlertRows, renderAlertInboxHtml } from "./alert-inbox";
import { buildSentimentAlerts } from "./sentiment-alerts";
import type { AmplificationReport, CibReport, ThemesReport } from "./types";

const emptyAmp: AmplificationReport = { narrative_id: 1, cluster_count: 0, clusters: [] };
const emptyThemes: ThemesReport = {
  available: true,
  reason: null,
  narrative_id: 1,
  post_count: 0,
  cluster_count: 0,
  method: "test",
  model: "test",
  clusters: [],
  timeline: [],
  emerging_theme_count: 0,
};

const baseCib: CibReport = {
  narrative_id: 1,
  suspicion_score: 0.2,
  organic_score: 0.8,
  text_coordination_score: 0.1,
  graph_suspicion_score: 0.1,
  graph_sufficient: false,
  graph_coverage_pct: 0,
  signals: [],
  text_signals: [],
  graph_signals: [],
  edge_count: 0,
  node_count: 0,
  density: 0,
  top_amplifiers: [],
  coordinated_clusters: [],
  iu_astroturf: {
    authors_in_narrative: 0,
    known_political_bots: 0,
    known_bot_ratio: 0,
    labeled_accounts: [],
    note: null,
  },
};

describe("buildAlertRows", () => {
  it("groups burst clusters as critical coordination", () => {
    const amp: AmplificationReport = {
      narrative_id: 1,
      cluster_count: 1,
      clusters: [
        {
          count: 4,
          author_count: 3,
          author_ids: ["a1"],
          post_ids: [1, 2, 3, 4],
          sample_text: "copy pasta text",
          burst_synchronized: true,
        },
      ],
    };
    const rows = buildAlertRows(amp, baseCib, null, null, emptyThemes);
    expect(rows[0]?.kind).toBe("burst");
    expect(rows[0]?.severity).toBe("critical");
    expect(rows[0]?.category).toBe("coordination");
    expect(rows[0]?.metric).toContain("4 posts");
  });
});

describe("renderAlertInboxHtml", () => {
  it("renders summary chips and grouped sections", () => {
    const html = renderAlertInboxHtml([
      {
        severity: "critical",
        category: "coordination",
        title: "Test",
        excerpt: "Sample",
        metric: "2 posts",
        count: 2,
        postIds: [1, 2],
        burst: false,
        kind: "duplicate",
      },
      {
        severity: "watch",
        category: "sentiment",
        title: "Trend",
        excerpt: "Up",
        metric: "5 days",
        count: 5,
        postIds: [],
        burst: false,
        kind: "sentiment",
      },
    ]);
    expect(html).toContain("alert-inbox-summary");
    expect(html).toContain("1 Critical");
    expect(html).toContain("Coordination");
    expect(html).toContain("Sentiment drift");
    expect(html).toContain("alert-inbox-card");
  });

  it("renders helpful empty state", () => {
    const html = renderAlertInboxHtml([]);
    expect(html).toContain("No elevated signals");
  });
});

describe("buildSentimentAlerts", () => {
  it("uses sentiment kind and filter date", () => {
    const rows = buildSentimentAlerts({
      narrative_id: 1,
      buckets: [],
      trend: "stable",
      divergence_days: [{ date: "2026-01-15", count: 12, mean_outrage: 0.12 }],
      week_over_week: { available: false },
    });
    expect(rows[0]?.kind).toBe("sentiment");
    expect(rows[0]?.filterDate).toBe("2026-01-15");
  });
});

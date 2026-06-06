import type { SentimentShift } from "./types";
import type { AlertRow } from "./alert-inbox";

export function buildSentimentAlerts(sentiment: SentimentShift): AlertRow[] {
  const rows: AlertRow[] = [];

  for (const day of sentiment.divergence_days ?? []) {
    rows.push({
      severity: "watch",
      category: "sentiment",
      title: "High volume, low outrage",
      excerpt: `Mean outrage ${day.mean_outrage.toFixed(3)} — possible narrative flooding without escalation.`,
      metric: `${day.count} posts · ${day.date}`,
      count: day.count,
      postIds: [],
      burst: false,
      kind: "sentiment",
      filterDate: day.date,
    });
  }

  const wow = sentiment.week_over_week;
  if (wow?.available && wow.alert) {
    if (wow.alert === "escalating_outrage") {
      rows.push({
        severity: "watch",
        category: "sentiment",
        title: "Escalating outrage (week-over-week)",
        excerpt: `Mean outrage rose from ${wow.prior_week_mean_outrage?.toFixed(3) ?? "?"} to ${wow.recent_week_mean_outrage?.toFixed(3) ?? "?"}.`,
        metric: `${wow.recent_week_posts ?? 0} posts this week`,
        count: wow.recent_week_posts ?? 0,
        postIds: [],
        burst: false,
        kind: "sentiment",
      });
    } else if (wow.alert === "volume_spike_low_outrage") {
      rows.push({
        severity: "context",
        category: "sentiment",
        title: "Volume spike, flat outrage",
        excerpt: `Post volume up ${wow.volume_delta_pct?.toFixed(0) ?? "?"}% week-over-week while outrage stayed low.`,
        metric: `${wow.recent_week_posts ?? 0} posts this week`,
        count: wow.recent_week_posts ?? 0,
        postIds: [],
        burst: false,
        kind: "sentiment",
      });
    }
  }

  if (sentiment.trend === "escalating") {
    rows.push({
      severity: "watch",
      category: "sentiment",
      title: "Upward sentiment trend",
      excerpt: "Daily mean outrage slope is positive across the snapshot window.",
      metric: `${sentiment.buckets.length} day${sentiment.buckets.length === 1 ? "" : "s"} tracked`,
      count: sentiment.buckets.length,
      postIds: [],
      burst: false,
      kind: "sentiment",
    });
  }

  return rows;
}

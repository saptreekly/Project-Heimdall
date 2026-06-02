import type { SentimentShift } from "./types";
import type { AlertRow } from "./alert-inbox";

export function buildSentimentAlerts(sentiment: SentimentShift): AlertRow[] {
  const rows: AlertRow[] = [];

  for (const day of sentiment.divergence_days ?? []) {
    rows.push({
      severity: "watch",
      title: "Volume without outrage",
      detail: `${day.date}: ${day.count} posts, mean outrage ${day.mean_outrage.toFixed(3)}`,
      count: day.count,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  const wow = sentiment.week_over_week;
  if (wow?.available && wow.alert) {
    if (wow.alert === "escalating_outrage") {
      rows.push({
        severity: "watch",
        title: "Escalating outrage (week-over-week)",
        detail: `Mean outrage up ${wow.mean_outrage_delta?.toFixed(3) ?? "?"} (${wow.prior_week_mean_outrage?.toFixed(3)} → ${wow.recent_week_mean_outrage?.toFixed(3)})`,
        count: wow.recent_week_posts ?? 0,
        postIds: [],
        burst: false,
        kind: "cib",
      });
    } else if (wow.alert === "volume_spike_low_outrage") {
      rows.push({
        severity: "context",
        title: "Volume spike, flat outrage",
        detail: `Post volume +${wow.volume_delta_pct?.toFixed(0) ?? "?"}% WoW while mean outrage stayed low`,
        count: wow.recent_week_posts ?? 0,
        postIds: [],
        burst: false,
        kind: "cib",
      });
    }
  }

  if (sentiment.trend === "escalating") {
    rows.push({
      severity: "watch",
      title: "Sentiment trend escalating",
      detail: "Daily mean outrage slope is significant over the snapshot window.",
      count: sentiment.buckets.length,
      postIds: [],
      burst: false,
      kind: "cib",
    });
  }

  return rows;
}

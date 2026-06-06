/** Site-wide notice for datasets containing harmful language (collapsed by default). */
export function renderContentNotice(): string {
  return `
    <details class="content-notice-collapse">
      <summary>Content notice — may include upsetting quoted material</summary>
      <aside class="content-notice" role="note" aria-label="Content notice">
        <p>
          This dashboard includes real social posts that may contain hate speech,
          slurs, or harassment. Material is shown for <strong>research and accountability</strong>
          only—not endorsement.
        </p>
        <p class="content-notice-sub">
          Nothing displayed here reflects the beliefs of the project maintainer.
        </p>
      </aside>
    </details>
  `;
}

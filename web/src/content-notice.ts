/** Site-wide notice for datasets containing harmful language (shown on every tab). */
export function renderContentNotice(): string {
  return `
    <aside class="content-notice" role="note" aria-label="Content notice">
      <p class="content-notice-title">Content notice</p>
      <p>
        This repository and dashboard include real social posts that may contain hate speech,
        slurs, harassment, or other language many people find upsetting. Quoted material is
        shown for <strong>research and accountability</strong> only: to document patterns,
        detect coordinated narratives, and support counter-messaging—not to amplify or endorse
        those views.
      </p>
      <p class="content-notice-sub">
        Nothing displayed here reflects the beliefs or views of the project maintainer.
      </p>
    </aside>
  `;
}

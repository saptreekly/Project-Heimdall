const STORAGE_KEY = "heimdall-onboarding-dismissed";

export function renderOnboardingHintHtml(): string {
  if (localStorage.getItem(STORAGE_KEY) === "1") return "";
  return `<aside class="onboarding-hint" id="onboarding-hint" role="note">
    <div class="onboarding-hint-inner">
      <strong>Quick start</strong>
      <ol class="onboarding-steps">
        <li>Pick a narrative above</li>
        <li>Scan the <em>Alert inbox</em> on Pulse <span class="onboarding-kbd">1</span></li>
        <li>Inspect frames in Frames <span class="onboarding-kbd">2</span> → Evidence <span class="onboarding-kbd">3</span> for posts</li>
        <li>Export from the <em>Briefing</em> tab when ready</li>
      </ol>
      <button type="button" id="dismiss-onboarding" class="btn btn-secondary btn-small">Dismiss</button>
    </div>
  </aside>`;
}

export function bindOnboardingHint(): void {
  document.getElementById("dismiss-onboarding")?.addEventListener("click", () => {
    localStorage.setItem(STORAGE_KEY, "1");
    document.getElementById("onboarding-hint")?.remove();
  });
}

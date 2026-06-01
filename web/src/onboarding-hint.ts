const STORAGE_KEY = "heimdall-onboarding-dismissed";

export function renderOnboardingHintHtml(): string {
  if (localStorage.getItem(STORAGE_KEY) === "1") return "";
  return `<aside class="onboarding-hint" id="onboarding-hint" role="note">
    <div class="onboarding-hint-inner">
      <strong>Quick start</strong>
      <ol class="onboarding-steps">
        <li>Pick a narrative above</li>
        <li>Scan the <em>Alert inbox</em> on Overview</li>
        <li>Click any signal → filtered Posts → <em>Briefing</em> tab to export</li>
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

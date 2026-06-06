const STORAGE_KEY = "heimdall-onboarding-dismissed";

export function renderOnboardingHintHtml(): string {
  if (localStorage.getItem(STORAGE_KEY) === "1") return "";
  return `<aside class="onboarding-hint" id="onboarding-hint" role="note">
    <div class="onboarding-hint-inner">
      <strong>Quick start</strong>
      <span class="onboarding-hint-text">
        Start on <em>Pulse</em> for alerts → <em>Frames</em> for themes → <em>Evidence</em> for posts.
        Keys <span class="onboarding-kbd">1</span>–<span class="onboarding-kbd">4</span> switch modes.
      </span>
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

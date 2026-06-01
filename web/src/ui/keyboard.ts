/** Activate clickable elements with Enter/Space (for non-button roles). */
export function bindKeyboardActivate(
  root: ParentNode,
  selector: string,
  handler: (el: HTMLElement) => void
): void {
  root.querySelectorAll<HTMLElement>(selector).forEach((el) => {
    if (el.tagName === "BUTTON" || el.tagName === "A") return;
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handler(el);
      }
    });
  });
}

/** Programmatic click for buttons and keyboard-activated elements. */
export function activateElement(el: HTMLElement): void {
  el.click();
}

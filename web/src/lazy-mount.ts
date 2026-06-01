/**
 * Run `mount` once when `target` intersects the viewport (or is already visible).
 */
export function observeLazyMount(target: Element | null, mount: () => void): void {
  if (!target) return;
  let done = false;
  const run = (): void => {
    if (done) return;
    done = true;
    mount();
  };

  if (isElementVisible(target)) {
    run();
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        run();
        io.disconnect();
      }
    },
    { rootMargin: "120px 0px", threshold: 0.05 }
  );
  io.observe(target);
}

function isElementVisible(el: Element): boolean {
  if (el.closest("[hidden]")) return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

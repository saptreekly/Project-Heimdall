import { deskModeFromUrl, deskModeList, type DeskMode } from "./desk-modes";

const SHORTCUT_TO_MODE: Record<string, DeskMode> = {
  "1": "pulse",
  "2": "frames",
  "3": "evidence",
  "4": "network",
};

export function bindDeskKeyboard(onModeChange: (mode: DeskMode) => void, onClearFilter: () => void): void {
  document.addEventListener("keydown", (e) => {
    const target = e.target as HTMLElement | null;
    if (!target) return;
    const tag = target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable) {
      return;
    }

    if (e.key === "Escape") {
      if (document.body.classList.contains("methodology-drawer-open")) return;
      onClearFilter();
      return;
    }

    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const mode = SHORTCUT_TO_MODE[e.key];
    if (mode) {
      e.preventDefault();
      onModeChange(mode);
    }
  });
}

export function bindMethodologyDrawer(): void {
  const drawer = document.getElementById("methodology-drawer");
  const openBtn = document.getElementById("open-methodology-drawer");
  const closeBtn = document.getElementById("close-methodology-drawer");
  const backdrop = document.getElementById("methodology-drawer-backdrop");

  const open = () => {
    drawer?.removeAttribute("hidden");
    backdrop?.removeAttribute("hidden");
    document.body.classList.add("methodology-drawer-open");
    closeBtn?.focus();
  };
  const close = () => {
    drawer?.setAttribute("hidden", "");
    backdrop?.setAttribute("hidden", "");
    document.body.classList.remove("methodology-drawer-open");
    openBtn?.focus();
  };

  openBtn?.addEventListener("click", open);
  closeBtn?.addEventListener("click", close);
  backdrop?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("methodology-drawer-open")) {
      close();
    }
  });
}

export function currentDeskModeFromKeyboard(): DeskMode {
  return deskModeFromUrl();
}

export function deskModeOrder(): DeskMode[] {
  return deskModeList();
}

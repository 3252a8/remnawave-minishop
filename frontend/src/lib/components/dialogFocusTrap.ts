const FOCUSABLE_SELECTOR =
  "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])";

export function focusFirstDialogControl(getDialog: () => HTMLElement | null): void {
  if (typeof window === "undefined") return;
  window.requestAnimationFrame(() => {
    getDialog()?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();
  });
}

export function handleDialogFocusTrap(
  event: KeyboardEvent,
  dialog: HTMLElement | null,
  onEscape: () => void
): void {
  if (!dialog || event.defaultPrevented) return;
  if (event.key === "Escape") {
    // Portalled menus handle Escape after it bubbles past the dialog trigger.
    if (dialog.querySelector('[aria-haspopup][aria-expanded="true"]')) return;
    event.preventDefault();
    onEscape();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1) || first;
  const outside = !dialog.contains(document.activeElement);
  if (event.shiftKey && (document.activeElement === first || outside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || outside)) {
    event.preventDefault();
    first.focus();
  }
}

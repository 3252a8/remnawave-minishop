type EventTargetLike = {
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

type DocumentLike = EventTargetLike & {
  visibilityState?: string;
};

type ResumeLifecycleDeps = {
  clearLoginTooltip: () => void;
  documentTarget?: DocumentLike | null;
  getMode: () => string;
  refreshPendingActivationOnResume: () => void;
  refreshTelegramNotificationsOnResume: () => void;
  windowTarget?: EventTargetLike | null;
};

export function createResumeLifecycle({
  clearLoginTooltip,
  documentTarget = typeof document === "undefined" ? null : document,
  getMode,
  refreshPendingActivationOnResume,
  refreshTelegramNotificationsOnResume,
  windowTarget = typeof window === "undefined" ? null : window,
}: ResumeLifecycleDeps) {
  function onAnyPointerDown() {
    if (getMode() === "login") clearLoginTooltip();
  }

  function onResume() {
    if (documentTarget?.visibilityState === "hidden") return;
    refreshPendingActivationOnResume();
    refreshTelegramNotificationsOnResume();
  }

  function onVisibilityChange() {
    if (documentTarget?.visibilityState !== "hidden") onResume();
  }

  function mount() {
    windowTarget?.addEventListener("pointerdown", onAnyPointerDown);
    windowTarget?.addEventListener("focus", onResume);
    windowTarget?.addEventListener("pageshow", onResume);
    documentTarget?.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      windowTarget?.removeEventListener("pointerdown", onAnyPointerDown);
      windowTarget?.removeEventListener("focus", onResume);
      windowTarget?.removeEventListener("pageshow", onResume);
      documentTarget?.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }

  return {
    mount,
    onAnyPointerDown,
    onResume,
    onVisibilityChange,
  };
}

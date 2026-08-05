import { shellState } from "./shellState.svelte";

type EventTargetLike = {
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

type DocumentLike = EventTargetLike & {
  documentElement?: {
    removeAttribute: (name: string) => void;
    toggleAttribute: (name: string, force?: boolean) => void;
  };
  visibilityState?: string;
};

/**
 * Telegram keeps the Mini App WebView alive between openings, so a session can
 * run for days on the payload fetched at boot — long after an admin changed
 * prices or switched a payment provider off. Re-reading it on resume is the
 * only thing that ends that, and the cooldown keeps a burst of focus events
 * from turning into a burst of requests.
 */
const ACCOUNT_REFRESH_COOLDOWN_MS = 15_000;

type ResumeLifecycleDeps = {
  accountRefreshCooldownMs?: number;
  clearLoginTooltip: () => void;
  documentTarget?: DocumentLike | null;
  now?: () => number;
  refreshAccountDataOnResume: () => void;
  refreshPendingActivationOnResume: () => void;
  refreshTelegramNotificationsOnResume: () => void;
  suspendBackgroundWork?: () => void;
  windowTarget?: EventTargetLike | null;
};

const APP_BACKGROUNDED_ATTRIBUTE = "data-app-backgrounded";

export function createResumeLifecycle({
  accountRefreshCooldownMs = ACCOUNT_REFRESH_COOLDOWN_MS,
  clearLoginTooltip,
  documentTarget = typeof document === "undefined" ? null : document,
  now = () => Date.now(),
  refreshAccountDataOnResume,
  refreshPendingActivationOnResume,
  refreshTelegramNotificationsOnResume,
  suspendBackgroundWork = () => {},
  windowTarget = typeof window === "undefined" ? null : window,
}: ResumeLifecycleDeps) {
  let lastAccountRefreshAt = 0;

  function onAnyPointerDown() {
    if (shellState.mode === "login") clearLoginTooltip();
  }

  function refreshAccountData() {
    // Nothing to refresh before sign-in, and the request would only 401.
    if (shellState.mode === "login") return;
    const timestamp = now();
    if (lastAccountRefreshAt && timestamp - lastAccountRefreshAt < accountRefreshCooldownMs) {
      return;
    }
    lastAccountRefreshAt = timestamp;
    refreshAccountDataOnResume();
  }

  function onResume() {
    if (documentTarget?.visibilityState === "hidden") return;
    refreshPendingActivationOnResume();
    refreshTelegramNotificationsOnResume();
    refreshAccountData();
  }

  function onVisibilityChange() {
    const backgrounded = documentTarget?.visibilityState === "hidden";
    documentTarget?.documentElement?.toggleAttribute(APP_BACKGROUNDED_ATTRIBUTE, backgrounded);
    if (backgrounded) {
      suspendBackgroundWork();
      return;
    }
    onResume();
  }

  function mount() {
    const backgrounded = documentTarget?.visibilityState === "hidden";
    documentTarget?.documentElement?.toggleAttribute(APP_BACKGROUNDED_ATTRIBUTE, backgrounded);
    if (backgrounded) suspendBackgroundWork();
    windowTarget?.addEventListener("pointerdown", onAnyPointerDown);
    windowTarget?.addEventListener("focus", onResume);
    windowTarget?.addEventListener("pageshow", onResume);
    documentTarget?.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      windowTarget?.removeEventListener("pointerdown", onAnyPointerDown);
      windowTarget?.removeEventListener("focus", onResume);
      windowTarget?.removeEventListener("pageshow", onResume);
      documentTarget?.removeEventListener("visibilitychange", onVisibilityChange);
      documentTarget?.documentElement?.removeAttribute(APP_BACKGROUNDED_ATTRIBUTE);
    };
  }

  return {
    mount,
    onAnyPointerDown,
    onResume,
    onVisibilityChange,
  };
}

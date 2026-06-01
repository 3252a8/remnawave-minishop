<script>
  import { onMount } from "svelte";

  import BrandMark from "$lib/webapp/BrandMark.svelte";

  const AUTO_OPEN_DELAY_MS = 80;
  const MANUAL_STATE_DELAY_MS = 1600;
  const DONE_STATE_DELAY_MS = 900;
  const CLOSE_ATTEMPT_DELAY_MS = 2500;

  export let brand = {};
  export let appLaunchTarget = "";
  export let refreshAppLaunchTarget = () => appLaunchTarget;
  export let openAppLaunchTarget = () => false;
  export let t = (_key, _params = {}, fallback = "") => fallback;

  let activeTarget = appLaunchTarget;
  let state = activeTarget ? "opening" : "unavailable";
  let attempted = false;
  let pageLeft = false;
  let autoOpenTimer = null;
  let manualStateTimer = null;
  let doneStateTimer = null;
  let closeAttemptTimer = null;

  $: if (!attempted && appLaunchTarget !== activeTarget) {
    activeTarget = appLaunchTarget;
    state = activeTarget ? "opening" : "unavailable";
  }

  $: isDone = state === "done";
  $: isUnavailable = state === "unavailable";
  $: title = isUnavailable
    ? t("wa_app_launch_unavailable_title", {}, "App link unavailable")
    : isDone
      ? t("wa_app_launch_done_title", {}, "Settings added")
      : t("wa_app_launch_title", {}, "Opening app");
  $: hint = isUnavailable
    ? t("wa_app_launch_unavailable_hint", {}, "Return to Telegram and try again.")
    : isDone
      ? t("wa_app_launch_done_hint", {}, "If the app opened, you can close this window.")
      : state === "manual"
        ? t(
            "wa_app_launch_hint",
            {},
            "If the app did not open automatically, tap the button below."
          )
        : t("wa_app_launch_opening_hint", {}, "Opening the app on this device...");
  $: openLabel = isDone
    ? t("wa_app_launch_retry_button", {}, "Open again")
    : t("wa_app_launch_button", {}, "Open app");

  onMount(() => {
    autoOpenTimer = window.setTimeout(openTarget, AUTO_OPEN_DELAY_MS);

    window.addEventListener("pagehide", notePageLeft);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearTimer(autoOpenTimer);
      clearTimer(manualStateTimer);
      clearTimer(doneStateTimer);
      clearTimer(closeAttemptTimer);
      window.removeEventListener("pagehide", notePageLeft);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  });

  function clearTimer(timer) {
    if (timer) window.clearTimeout(timer);
  }

  function refreshTarget() {
    const target = String(refreshAppLaunchTarget?.() || appLaunchTarget || "").trim();
    activeTarget = target;
    if (!activeTarget) state = "unavailable";
    return activeTarget;
  }

  function tryCloseWindow() {
    try {
      window.close();
    } catch (_error) {
      void _error;
    }
  }

  function markDone() {
    if (!attempted || state === "done" || !activeTarget) return;
    state = "done";
    clearTimer(closeAttemptTimer);
    closeAttemptTimer = window.setTimeout(() => {
      if (pageLeft || document.hidden) tryCloseWindow();
    }, CLOSE_ATTEMPT_DELAY_MS);
  }

  function notePageLeft() {
    if (!attempted) return;
    pageLeft = true;
    clearTimer(doneStateTimer);
    doneStateTimer = window.setTimeout(markDone, DONE_STATE_DELAY_MS);
  }

  function handleVisibilityChange() {
    if (!attempted) return;
    if (document.hidden) {
      pageLeft = true;
      return;
    }
    if (pageLeft) markDone();
  }

  function openTarget() {
    const target = refreshTarget();
    if (!target) {
      state = "unavailable";
      return;
    }

    attempted = true;
    pageLeft = false;
    state = "opening";
    openAppLaunchTarget(target);

    clearTimer(manualStateTimer);
    manualStateTimer = window.setTimeout(() => {
      if (state === "opening" && !pageLeft) state = "manual";
    }, MANUAL_STATE_DELAY_MS);
  }

  function closeWindow() {
    tryCloseWindow();
    state = "done";
  }
</script>

<div class="app-launch-shell">
  <main class="app-launch-panel">
    <div class="app-launch-brand" aria-hidden="true">
      <BrandMark {brand} size="md" />
    </div>
    <h1>{title}</h1>
    <p>{hint}</p>
    <div class="app-launch-actions">
      <a
        class="app-launch-button"
        class:disabled={isUnavailable}
        href={activeTarget || "#"}
        aria-disabled={isUnavailable ? "true" : undefined}
        rel="noreferrer"
        onclick={(event) => {
          event.preventDefault();
          if (!isUnavailable) openTarget();
        }}
      >
        {openLabel}
      </a>
      {#if isDone}
        <button class="app-launch-button secondary" type="button" onclick={closeWindow}>
          {t("wa_app_launch_close_button", {}, "Close window")}
        </button>
      {/if}
    </div>
  </main>
</div>

<style>
  .app-launch-shell {
    display: grid;
    min-height: 100dvh;
    place-items: center;
    padding: max(24px, env(safe-area-inset-top)) max(18px, env(safe-area-inset-right))
      max(24px, env(safe-area-inset-bottom)) max(18px, env(safe-area-inset-left));
    box-sizing: border-box;
  }

  .app-launch-panel {
    display: grid;
    width: min(100%, 420px);
    gap: 14px;
    justify-items: center;
    text-align: center;
  }

  .app-launch-brand {
    margin-bottom: 4px;
  }

  .app-launch-panel h1 {
    margin: 0;
    color: var(--text);
    font-size: 24px;
    line-height: 1.18;
  }

  .app-launch-panel p {
    margin: 0;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.55;
  }

  .app-launch-actions {
    display: grid;
    width: 100%;
    gap: 10px;
    margin-top: 4px;
  }

  .app-launch-button {
    display: inline-flex;
    width: 100%;
    min-height: 48px;
    align-items: center;
    justify-content: center;
    border: 1px solid transparent;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-contrast);
    padding: 0 18px;
    box-sizing: border-box;
    font: inherit;
    font-size: 15px;
    font-weight: 850;
    text-decoration: none;
    cursor: pointer;
  }

  .app-launch-button.secondary {
    border-color: var(--border-strong);
    background: transparent;
    color: var(--text);
  }

  .app-launch-button.disabled {
    pointer-events: none;
    border-color: transparent;
    background: var(--panel-3);
    color: var(--muted);
  }
</style>

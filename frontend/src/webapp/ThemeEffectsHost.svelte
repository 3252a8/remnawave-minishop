<script lang="ts">
  import { onMount, untrack } from "svelte";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import { buildThemeEffectsPath, unwrap } from "$lib/webapp/publicApi";
  import {
    setThemeEffectsDisabled,
    setThemeEffectsFailure,
    themeEffectsStatus,
    type ThemeEffectsSettings,
  } from "$lib/webapp/themeEffectsPreference";
  import {
    createThemeEffectsRuntime,
    type ThemeEffectDescriptor,
  } from "$lib/webapp/themeEffectsRuntime";
  import type { ThemeEffectContext } from "$lib/webapp/themeEffectsSdk";

  let {
    client,
    enabled,
    userToggleEnabled,
    identity,
    themeKey,
    previewKey,
    context,
    onSettingsChange,
  }: {
    client: ApiClient;
    enabled: boolean;
    userToggleEnabled: boolean;
    identity: string;
    themeKey: string;
    previewKey: string;
    context: ThemeEffectContext;
    onSettingsChange: (settings: ThemeEffectsSettings | null) => void;
  } = $props();

  const runtime = createThemeEffectsRuntime();
  let activeDescriptor: ThemeEffectDescriptor | null = null;
  let request: AbortController | null = null;
  let reducedMotion = false;
  let ready = false;
  let mounted = false;
  let leaving = false;

  function stop(resetDocument: boolean) {
    request?.abort();
    request = null;
    mounted = false;
    if (leaving) return;
    void runtime.dispose();
    if (resetDocument && runtime.executed) {
      leaving = true;
      location.reload();
    }
  }

  function publishSettings(descriptor: ThemeEffectDescriptor) {
    const status = themeEffectsStatus(
      descriptor.key,
      descriptor.digest,
      reducedMotion,
      userToggleEnabled
    );
    onSettingsChange(userToggleEnabled ? { status, setEnabled } : null);
    return status;
  }

  function preferenceChanged() {
    if (leaving || !activeDescriptor) return;
    if (publishSettings(activeDescriptor) === "enabled") void refresh();
    else if (request || runtime.executed) stop(true);
  }

  function setEnabled(next: boolean) {
    if (!userToggleEnabled || !activeDescriptor || leaving) return;
    setThemeEffectsDisabled(activeDescriptor.key, !next);
    if (next) setThemeEffectsFailure(activeDescriptor.key, null);
    preferenceChanged();
  }

  function fail(descriptor: ThemeEffectDescriptor) {
    if (
      leaving ||
      activeDescriptor?.key !== descriptor.key ||
      activeDescriptor.digest !== descriptor.digest
    )
      return;
    setThemeEffectsFailure(descriptor.key, descriptor.digest);
    publishSettings(descriptor);
    stop(true);
  }

  async function refresh() {
    if (!ready || leaving || !enabled || document.hidden || request) return;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
      let descriptor: ThemeEffectDescriptor | null;
      try {
        const result = unwrap(
          await client.api(buildThemeEffectsPath(previewKey), { signal: controller.signal })
        );
        descriptor = result.effect ?? null;
      } catch {
        // Revalidate on the next poll or resume. A running script must not
        // stay active when we can no longer check its permission.
        if (request === controller && runtime.executed) stop(true);
        return;
      } finally {
        clearTimeout(timeout);
      }
      if (request !== controller || !enabled || document.hidden) return;
      if (!descriptor || descriptor.key !== themeKey) {
        activeDescriptor = null;
        onSettingsChange(null);
        if (runtime.executed) stop(true);
        return;
      }
      if (runtime.executed && descriptor.digest !== runtime.digest) {
        stop(true);
        return;
      }
      activeDescriptor = descriptor;
      if (publishSettings(descriptor) !== "enabled" || mounted) return;
      try {
        await runtime.start(descriptor, context);
        if (request !== controller) return;
        mounted = true;
        await runtime.update(context);
      } catch {
        if (request === controller) fail(descriptor);
      }
    } finally {
      if (request === controller) request = null;
    }
  }

  $effect(() => {
    void enabled;
    void identity;
    void themeKey;
    void previewKey;
    untrack(() => {
      activeDescriptor = null;
      onSettingsChange(null);
      stop(true);
      void refresh();
    });
  });

  $effect(() => {
    const descriptor = activeDescriptor;
    void runtime.update(context).catch(() => {
      if (descriptor) fail(descriptor);
    });
  });

  onMount(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    ready = true;
    reducedMotion = media.matches;
    const visibility = () => {
      if (document.hidden) stop(false);
      else void refresh();
    };
    const motion = () => {
      reducedMotion = media.matches;
      preferenceChanged();
    };
    document.addEventListener("visibilitychange", visibility);
    media.addEventListener("change", motion);
    window.addEventListener("storage", preferenceChanged);
    const interval = setInterval(() => void refresh(), 30_000);
    void refresh();
    return () => {
      ready = false;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", visibility);
      media.removeEventListener("change", motion);
      window.removeEventListener("storage", preferenceChanged);
      stop(false);
    };
  });
</script>

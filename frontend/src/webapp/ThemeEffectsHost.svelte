<script lang="ts">
  import { onMount } from "svelte";
  import { Button } from "$components/ui/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import { unwrap } from "$lib/webapp/publicApi";
  import {
    createThemeEffectsRuntime,
    themeEffectsDisabled,
    THEME_EFFECTS_STORAGE,
  } from "$lib/webapp/themeEffectsRuntime";
  import type { ThemeEffectContext } from "$lib/webapp/themeEffectsSdk";
  let {
    client,
    enabled,
    identity,
    themeKey,
    context,
    t,
  }: {
    client: ApiClient;
    enabled: boolean;
    identity: string;
    themeKey: string;
    context: ThemeEffectContext;
    t: (key: string) => string;
  } = $props();
  const runtime = createThemeEffectsRuntime();
  let hasEffect = $state(false);
  let locallyDisabled = $state(false);
  let refresh: () => Promise<void> = async () => {};
  let cancelRequest = () => {};
  let lastIdentity = "";
  let failed = false;
  let leaving = false;
  let mounted = false;
  function reload(off: boolean) {
    if (leaving) return;
    leaving = true;
    const url = new URL(location.href);
    if (off) url.searchParams.set("theme_effects", "off");
    else url.searchParams.delete("theme_effects");
    location.replace(url.href);
  }
  async function stop(resetDocument: boolean) {
    cancelRequest();
    mounted = false;
    const executed = runtime.executed;
    const cleanup = runtime.dispose();
    if (resetDocument && executed) reload(true);
    await cleanup;
  }
  $effect(() => {
    void enabled;
    void identity;
    void themeKey;
    if (!enabled || (runtime.executed && lastIdentity !== identity)) void stop(true);
    else void refresh();
  });
  $effect(() => {
    void runtime.update(context).catch(async () => {
      failed = true;
      await stop(true);
    });
  });
  onMount(() => {
    locallyDisabled = themeEffectsDisabled();
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    let disposed = false;
    let request: AbortController | null = null;
    let revision = 0;
    cancelRequest = () => {
      revision++;
      request?.abort();
      request = null;
    };
    refresh = async () => {
      if (disposed || leaving) return;
      if (!enabled || locallyDisabled || media.matches || document.hidden || failed) {
        await stop(!enabled || locallyDisabled || failed);
        return;
      }
      if (request) return;
      const current = ++revision;
      const account = identity;
      const selected = themeKey;
      const controller = new AbortController();
      request = controller;
      const timeout = setTimeout(() => controller.abort(), 10_000);
      try {
        const result = unwrap(await client.api("/theme-effects", { signal: controller.signal }));
        if (
          disposed ||
          current !== revision ||
          !enabled ||
          account !== identity ||
          selected !== themeKey ||
          document.hidden ||
          media.matches ||
          locallyDisabled
        )
          return;
        const effect = result.effect;
        hasEffect = Boolean(effect);
        if (
          !effect ||
          effect.key !== themeKey ||
          (runtime.executed && effect.digest !== runtime.digest)
        ) {
          await stop(true);
          return;
        }
        if (!mounted) {
          lastIdentity = identity;
          await runtime.start(effect, context);
          if (current === revision) {
            mounted = true;
            await runtime.update(context);
          }
        }
      } catch {
        if (!disposed && current === revision) {
          failed = true;
          await stop(true);
        }
      } finally {
        clearTimeout(timeout);
        if (current === revision) request = null;
      }
    };
    const visibility = () => {
      void refresh();
    };
    const storage = () => {
      locallyDisabled = themeEffectsDisabled();
      void refresh();
    };
    document.addEventListener("visibilitychange", visibility);
    media.addEventListener("change", visibility);
    window.addEventListener("storage", storage);
    const interval = setInterval(() => {
      void refresh();
    }, 30_000);
    void refresh();
    return () => {
      disposed = true;
      cancelRequest();
      clearInterval(interval);
      document.removeEventListener("visibilitychange", visibility);
      media.removeEventListener("change", visibility);
      window.removeEventListener("storage", storage);
      void runtime.dispose();
    };
  });
  function toggle() {
    locallyDisabled = !locallyDisabled;
    try {
      localStorage.setItem(THEME_EFFECTS_STORAGE, locallyDisabled ? "1" : "0");
    } catch {
      /* The URL also carries the preference for this document. */
    }
    void runtime.dispose();
    reload(locallyDisabled);
  }
</script>

{#if enabled && (hasEffect || locallyDisabled)}
  <div class="theme-effects-control">
    <Button variant="outline" onclick={toggle}
      >{t(locallyDisabled ? "wa_theme_effects_enable" : "wa_theme_effects_disable")}</Button
    >
  </div>
{/if}

<style>
  .theme-effects-control {
    position: fixed;
    right: max(12px, var(--content-safe-area-right, 0px));
    bottom: calc(84px + var(--content-safe-area-bottom, 0px));
    z-index: 55;
    display: flex;
    justify-content: center;
    padding: 0.75rem;
    font-size: 0.8rem;
  }
</style>

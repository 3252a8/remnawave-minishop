<script lang="ts">
  import { onDestroy } from "svelte";
  import { getThemesStore } from "$lib/admin/context";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Dialog } from "$components/ui/index.js";
  let {
    themeKey,
    importId,
    at,
  }: {
    themeKey: string;
    importId?: string;
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  } = $props();
  const library = getThemesStore().library;
  let open = $state(false);
  let source = $state("");
  let loading = $state(false);
  let error = $state("");
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  function clear() {
    generation++;
    clearTimeout(timer);
    source = "";
    loading = false;
  }
  function close() {
    clear();
    open = false;
    error = "";
  }
  async function run() {
    clear();
    error = "";
    loading = true;
    const current = generation;
    try {
      const page = await library.previewEffects(themeKey, importId);
      if (open && current === generation) {
        source = page;
        timer = setTimeout(clear, 60_000);
      }
    } catch (cause) {
      if (current === generation) error = library.message(cause);
    } finally {
      if (current === generation) loading = false;
    }
  }
  onDestroy(clear);
</script>

<AdminButton size="sm" variant="default" onclick={() => (open = true)}
  >{at("theme_effects_preview")}</AdminButton
>
<Dialog portal {open} title={at("theme_effects_preview")} closeLabel={at("close")} onclose={close}>
  <p>{at("theme_effects_preview_notice")}</p>
  <AdminButton disabled={loading} onclick={run}>{at("theme_effects_preview_run")}</AdminButton>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if source}
    <iframe
      title={at("theme_effects_preview")}
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      srcdoc={source}
    ></iframe>
  {/if}
</Dialog>

<style>
  iframe {
    width: 100%;
    height: min(60vh, 580px);
    border: 0;
    margin-top: 1rem;
    border-radius: 1rem;
  }
</style>

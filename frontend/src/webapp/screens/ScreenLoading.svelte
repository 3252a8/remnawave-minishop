<script lang="ts">
  import { Button, Spinner } from "$components/ui/index.js";
  import type { LazyScreen } from "$lib/webapp/lazyScreen.svelte.js";

  /**
   * Placeholder for a screen whose code is still downloading.
   *
   * Screens are fetched on first open, so this is what the customer sees for
   * the fraction of a second between tapping a tab and its chunk arriving —
   * and for longer on a bad connection, which is why it says what it is doing.
   */
  let { screen, t }: { screen: LazyScreen<unknown>; t: (key: string) => string } = $props();
</script>

<main
  class="content with-nav screen-loading"
  role={screen.failed ? "alert" : "status"}
  aria-live="polite"
>
  {#if screen.failed}
    <span>{t("wa_screen_load_failed")}</span>
    <Button onclick={screen.load}>{t("wa_retry")}</Button>
  {:else}
    <Spinner size="lg" />
    <span>{t("wa_loading")}</span>
  {/if}
</main>

<style>
  .screen-loading {
    display: flex;
    flex-direction: column;
    gap: 12px;
    align-items: center;
    justify-content: center;
    min-height: 40vh;
    color: var(--muted);
    font-size: 13px;
  }
</style>

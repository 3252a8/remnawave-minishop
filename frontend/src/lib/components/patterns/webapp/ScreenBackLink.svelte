<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import { ArrowLeft } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";

  // The single "back" control for cabinet sub-screens: a square button at the
  // start of the title row, so going back never costs a line of its own.
  let {
    label,
    onclick,
    railItem = false,
    class: className = "",
  }: {
    label: string;
    onclick: () => void;
    /** The screen is listed in the desktop sidebar, which already shows where you are. */
    railItem?: boolean;
    class?: string;
  } = $props();
</script>

<Button
  variant="secondary"
  size="icon"
  class={cn("screen-back-link", railItem && "is-rail-item", className)}
  aria-label={label}
  title={label}
  {onclick}
>
  <ArrowLeft size={20} aria-hidden="true" />
</Button>

<style>
  :global(.btn.screen-back-link) {
    flex: 0 0 auto;
    color: var(--text);
  }

  @media (min-width: 1024px) {
    :global(.btn.screen-back-link.is-rail-item) {
      display: none;
    }
  }
</style>

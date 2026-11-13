<script lang="ts">
  import { ArrowLeft } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";

  // The single "back" control for cabinet sub-screens, so every one starts at the
  // same position with the same weight.
  let {
    label,
    onclick,
    class: className = "",
  }: {
    label: string;
    onclick: () => void;
    class?: string;
  } = $props();
</script>

<button class={cn("screen-back-link", className)} type="button" {onclick}>
  <ArrowLeft size={18} aria-hidden="true" />
  {label}
</button>

<style>
  .screen-back-link {
    display: inline-flex;
    align-items: center;
    justify-self: start;
    gap: 6px;
    min-height: 36px;
    padding: 0 4px;
    border: 0;
    border-radius: var(--radius-inner);
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }

  .screen-back-link:hover {
    color: var(--text);
  }

  .screen-back-link:focus-visible {
    outline: 2px solid color-mix(in srgb, var(--accent) 60%, transparent);
    outline-offset: 2px;
  }
</style>

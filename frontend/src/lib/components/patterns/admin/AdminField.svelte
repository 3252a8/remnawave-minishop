<script lang="ts">
  import { Label } from "$components/ui/primitives.js";
  import type { Snippet } from "svelte";

  type Props = {
    children?: Snippet;
    hint?: string;
    label?: string;
  };

  let { label = "", hint = "", children }: Props = $props();
</script>

<div class="admin-field">
  <Label.Root class="admin-field-label">
    {#if label}<span>{label}</span>{/if}
    {@render children?.()}
    {#if hint}<small>{hint}</small>{/if}
  </Label.Root>
</div>

<style>
  .admin-field {
    min-width: 0;
  }
  .admin-field :global(.admin-field-label) {
    display: grid;
    gap: 6px;
    min-width: 0;
    align-content: start;
  }
</style>

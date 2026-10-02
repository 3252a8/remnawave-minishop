<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  let {
    columns = 2,
    minWidth = "180px",
    class: className = "",
    children,
  }: {
    columns?: number;
    minWidth?: string;
    class?: string;
    children?: Snippet;
  } = $props();
</script>

<div
  class={cn("admin-form-grid", className)}
  data-columns={columns}
  style={`--form-columns: ${columns}; --form-min-width: ${minWidth}`}
>
  {@render children?.()}
</div>

<style>
  .admin-form-grid {
    display: grid;
    grid-template-columns: repeat(
      var(--form-columns),
      minmax(min(var(--form-min-width), 100%), 1fr)
    );
    align-items: start;
    gap: 16px;
    min-width: 0;
  }
  .admin-form-grid :global(.admin-field-label) {
    display: grid;
    align-content: start;
    gap: 6px;
    min-width: 0;
  }
  .admin-form-grid :global(.input),
  .admin-form-grid :global(.admin-select-trigger) {
    width: 100%;
    min-width: 0;
    height: 40px;
    min-height: 40px;
  }
  @media (min-width: 721px) and (max-width: 1100px) {
    .admin-form-grid[data-columns="3"],
    .admin-form-grid[data-columns="4"] {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 720px) {
    .admin-form-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>

<script lang="ts">
  import { ArrowDown, ArrowUp, ChevronsUpDown } from "$components/ui/icons.js";

  type SortState = "none" | "ascending" | "descending";
  type Props = {
    label: string;
    state?: SortState;
    title?: string;
    onclick?: () => void;
  };

  let { label, state = "none", title = "", onclick = () => {} }: Props = $props();
</script>

<!-- Column-header toggle for sortable admin tables; render inside a <th>
     that carries the matching aria-sort attribute. -->
<button type="button" class="admin-sort-header" title={title || undefined} {onclick}>
  <span>{label}</span>
  <span class="admin-sort-state" data-state={state} aria-hidden="true">
    {#if state === "ascending"}
      <ArrowUp size={13} />
    {:else if state === "descending"}
      <ArrowDown size={13} />
    {:else}
      <ChevronsUpDown size={13} />
    {/if}
  </span>
</button>

<style>
  .admin-sort-header {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    max-width: 100%;
    margin: -4px -6px;
    padding: 4px 6px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: inherit;
    font: inherit;
    letter-spacing: inherit;
    text-transform: inherit;
    cursor: pointer;
  }

  .admin-sort-header:hover,
  .admin-sort-header:focus-visible {
    color: var(--admin-text);
    background: color-mix(in srgb, var(--admin-muted) 10%, transparent);
    outline: none;
  }

  .admin-sort-header:focus-visible {
    box-shadow: 0 0 0 2px var(--admin-ring);
  }

  .admin-sort-state {
    display: inline-flex;
    align-items: center;
    color: var(--admin-dim);
  }

  .admin-sort-state[data-state="ascending"],
  .admin-sort-state[data-state="descending"] {
    color: color-mix(in srgb, var(--accent) 72%, var(--admin-muted));
  }
</style>

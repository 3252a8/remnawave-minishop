<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  let {
    search,
    searchActions,
    mobileFilters,
    filters,
    actions,
    metadata,
    footer,
    total,
    totalLabel,
    columns = 3,
    mobileFilterMode = "inline",
    onsubmit,
    class: className = "",
  }: {
    search?: Snippet;
    searchActions?: Snippet;
    mobileFilters?: Snippet;
    filters?: Snippet;
    actions?: Snippet;
    metadata?: Snippet;
    footer?: Snippet;
    total?: number;
    totalLabel?: string;
    columns?: number;
    mobileFilterMode?: "inline" | "dialog";
    onsubmit?: (event: SubmitEvent) => void;
    class?: string;
  } = $props();
</script>

{#snippet summary()}
  <div class="admin-list-toolbar-summary">
    <span>{totalLabel}</span><strong>{total}</strong>
  </div>
{/snippet}

<form
  class={cn("admin-list-toolbar", className)}
  data-mobile-filters={mobileFilterMode}
  style={`--toolbar-columns: ${columns}; --toolbar-mobile-columns: ${Math.min(2, columns)}`}
  onsubmit={(event) => {
    event.preventDefault();
    onsubmit?.(event);
  }}
>
  {#if search}
    <div class="admin-list-toolbar-search">
      <div class="admin-list-toolbar-input">{@render search()}</div>
      {@render searchActions?.()}
      {#if mobileFilters}<div class="admin-list-toolbar-mobile">{@render mobileFilters()}</div>{/if}
    </div>
  {/if}
  {#if filters || actions || metadata || total !== undefined}
    <div class="admin-list-toolbar-controls" class:without-filters={!filters}>
      {#if filters}<div class="admin-list-toolbar-filters">{@render filters()}</div>{/if}
      {#if total !== undefined}{@render summary()}{/if}
      {#if actions}<div class="admin-list-toolbar-actions">{@render actions()}</div>{/if}
      {#if metadata}<div class="admin-list-toolbar-metadata">{@render metadata()}</div>{/if}
    </div>
  {/if}
  {@render footer?.()}
</form>

<style>
  .admin-list-toolbar {
    display: grid;
    gap: 12px;
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-card-bg);
    box-shadow: var(--admin-card-shadow);
  }
  .admin-list-toolbar-search {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .admin-list-toolbar-input {
    flex: 1;
    min-width: 0;
  }
  .admin-list-toolbar :global(.input),
  .admin-list-toolbar :global(.admin-btn),
  .admin-list-toolbar :global(.admin-select-trigger) {
    height: 36px;
    min-height: 36px;
  }
  .admin-list-toolbar-input :global(.input) {
    width: 100%;
  }
  .admin-list-toolbar-controls {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: 12px;
    min-width: 0;
  }
  .admin-list-toolbar-filters {
    display: grid;
    grid-template-columns: repeat(var(--toolbar-columns), minmax(0, 1fr));
    flex: 1;
    gap: 12px;
    min-width: 0;
  }
  .admin-list-toolbar-filters :global(.admin-field-label > span) {
    color: var(--admin-muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }
  .admin-list-toolbar-summary {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    font-size: 14px;
    white-space: nowrap;
  }
  .admin-list-toolbar-summary > span {
    color: var(--admin-muted);
    font-size: 13px;
  }
  .admin-list-toolbar-summary > strong {
    font-variant-numeric: tabular-nums;
  }
  .without-filters .admin-list-toolbar-summary {
    margin-right: auto;
  }
  .admin-list-toolbar-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .admin-list-toolbar-mobile {
    display: none;
  }
  .admin-list-toolbar-metadata {
    margin-left: auto;
    min-width: 0;
    align-self: center;
    text-align: right;
  }
  @media (max-width: 720px) {
    .admin-list-toolbar-metadata {
      flex-basis: 100%;
      margin-left: 0;
      text-align: left;
    }
    .admin-list-toolbar-controls:not(.without-filters) {
      flex-wrap: wrap;
    }
    .admin-list-toolbar-filters {
      flex-basis: 100%;
      grid-template-columns: repeat(var(--toolbar-mobile-columns), minmax(0, 1fr));
    }
    .admin-list-toolbar-summary {
      margin-right: auto;
    }
    [data-mobile-filters="dialog"] .admin-list-toolbar-filters {
      display: none;
    }
    .admin-list-toolbar-mobile {
      display: flex;
    }
  }
</style>

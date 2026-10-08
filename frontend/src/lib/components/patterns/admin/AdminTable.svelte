<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";
  import type { HTMLTableAttributes } from "svelte/elements";

  type Props = Omit<HTMLTableAttributes, "children" | "class"> & {
    children?: Snippet;
    class?: string;
    skeleton?: boolean;
    layout?: "auto" | "fixed";
    minWidth?: string;
    appearance?: "admin" | "webapp";
  };

  let {
    skeleton = false,
    layout = "auto",
    minWidth = "760px",
    appearance = "admin",
    class: className = "",
    children,
    ...restProps
  }: Props = $props();
</script>

<div
  class="admin-table-wrap"
  class:webapp-table-wrap={appearance === "webapp"}
  style={`--admin-table-min-width: ${minWidth}`}
>
  <table
    class={cn(
      "admin-table",
      skeleton && "admin-table-skeleton",
      layout === "fixed" && "admin-table-fixed",
      className
    )}
    aria-hidden={skeleton ? "true" : undefined}
    {...restProps}
  >
    {@render children?.()}
  </table>
</div>

<style>
  .admin-table-wrap {
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
  }
  .webapp-table-wrap {
    border: 1px solid var(--border);
    border-radius: var(--radius-inner);
    background: var(--panel);
  }
  .webapp-table-wrap table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .webapp-table-wrap :global(th),
  .webapp-table-wrap :global(td) {
    padding: 14px 12px;
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid var(--border);
    overflow-wrap: anywhere;
  }
  .webapp-table-wrap :global(th) {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    background: var(--panel-2);
  }
  .webapp-table-wrap :global(tbody tr:last-child td) {
    border-bottom: 0;
  }
  .webapp-table-wrap :global(td[data-numeric]) {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  @media (min-width: 721px) {
    .admin-table-fixed {
      table-layout: fixed;
      min-width: var(--admin-table-min-width);
    }
    .admin-table-fixed :global(th) {
      white-space: normal;
      overflow-wrap: normal;
    }
    .admin-table-fixed :global(td) {
      white-space: normal;
      overflow-wrap: anywhere;
    }
  }
  @media (max-width: 720px) {
    .webapp-table-wrap {
      border: 0;
      background: transparent;
    }
    .webapp-table-wrap :global(thead) {
      display: none;
    }
    .webapp-table-wrap table,
    .webapp-table-wrap :global(tbody) {
      display: block;
    }
    .webapp-table-wrap :global(tbody) {
      display: grid;
      gap: 12px;
    }
    .webapp-table-wrap :global(tr) {
      display: grid;
      gap: 10px;
      padding: 16px;
      border: 1px solid var(--border);
      border-radius: var(--radius-inner);
      background: var(--panel);
    }
    .webapp-table-wrap :global(td) {
      display: grid;
      grid-template-columns: minmax(0, 35%) minmax(0, 1fr);
      align-items: start;
      gap: 12px;
      min-width: 0;
      padding: 0;
      border: 0;
    }
    .webapp-table-wrap :global(td::before) {
      content: attr(data-label);
      color: var(--muted);
      font-size: 12px;
      white-space: normal;
    }
    .admin-table-fixed :global(colgroup) {
      display: none;
    }
  }
</style>

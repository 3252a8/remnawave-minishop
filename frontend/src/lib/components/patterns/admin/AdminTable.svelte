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
  };

  let {
    skeleton = false,
    layout = "auto",
    minWidth = "760px",
    class: className = "",
    children,
    ...restProps
  }: Props = $props();
</script>

<div class="admin-table-wrap" style={`--admin-table-min-width: ${minWidth}`}>
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
    .admin-table-fixed :global(colgroup) {
      display: none;
    }
  }
</style>

<script lang="ts">
  import type { AdminSortSpec } from "$lib/admin/tableSort.js";
  import { adminSortState, adminSortTitle, nextAdminSort } from "$lib/admin/tableSort.js";
  import AdminSortHeader from "./AdminSortHeader.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    label,
    column,
    currentSort = "",
    at = (key, _params, fallback) => fallback || key,
    onSort = () => {},
    class: className = "",
  }: {
    label: string;
    column: AdminSortSpec;
    currentSort?: string;
    at?: TranslateFn;
    onSort?: (sort: string) => void;
    class?: string;
  } = $props();

  const state = $derived(adminSortState(currentSort, column));
</script>

<th aria-sort={state} class={className || undefined}>
  <AdminSortHeader
    {label}
    {state}
    title={adminSortTitle(state, at)}
    onclick={() => onSort(nextAdminSort(currentSort, column))}
  />
</th>

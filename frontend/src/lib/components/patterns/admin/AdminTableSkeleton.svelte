<script lang="ts">
  import Skeleton from "$components/ui/skeleton.svelte";
  import AdminTable from "./AdminTable.svelte";

  type Props = {
    headers?: string[];
    rows?: number;
    actionColumn?: boolean;
    widths?: string[];
    class?: string;
    rowHeight?: number;
    preserveRowHeightOnMobile?: boolean;
  };

  let {
    headers = [],
    rows = 6,
    actionColumn = false,
    widths = [],
    class: className = "",
    rowHeight = 48,
    preserveRowHeightOnMobile = false,
  }: Props = $props();

  const tableClass = $derived(
    [className, preserveRowHeightOnMobile ? "admin-table-skeleton--fixed-mobile-rows" : ""]
      .filter(Boolean)
      .join(" ")
  );

  function widthFor(index: number): string {
    if (widths[index]) return widths[index];
    if (actionColumn && index === headers.length - 1) return "92px";
    if (index === 0) return "48px";
    if (index === headers.length - 1) return "76px";
    return index % 3 === 0 ? "56%" : "72%";
  }
</script>

<AdminTable skeleton class={tableClass} style={`--admin-table-skeleton-row-height:${rowHeight}px`}>
  <thead>
    <tr>
      {#each headers as header}
        <th class:admin-cell-actions={actionColumn && header === headers[headers.length - 1]}
          >{header}</th
        >
      {/each}
    </tr>
  </thead>
  <tbody>
    {#each Array(rows) as _, rowIndex (rowIndex)}
      <tr>
        {#each headers as _header, colIndex (`${rowIndex}-${colIndex}`)}
          <td data-label={_header}>
            <Skeleton variant="line" width={widthFor(colIndex)} />
          </td>
        {/each}
      </tr>
    {/each}
  </tbody>
</AdminTable>

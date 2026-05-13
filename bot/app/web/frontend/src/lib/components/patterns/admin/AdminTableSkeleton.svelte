<script>
  import Skeleton from "$components/ui/skeleton.svelte";
  import AdminTable from "./AdminTable.svelte";

  export let headers = [];
  export let rows = 6;
  export let actionColumn = false;
  export let widths = [];

  function widthFor(index) {
    if (widths[index]) return widths[index];
    if (actionColumn && index === headers.length - 1) return "92px";
    if (index === 0) return "48px";
    if (index === headers.length - 1) return "76px";
    return index % 3 === 0 ? "56%" : "72%";
  }
</script>

<AdminTable skeleton>
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
          <td>
            <Skeleton variant="line" width={widthFor(colIndex)} />
          </td>
        {/each}
      </tr>
    {/each}
  </tbody>
</AdminTable>

<script lang="ts">
  import { ArrowRight, ChevronLeft, ChevronRight } from "$components/ui/icons.js";
  import { watchAdminDatatable } from "$lib/admin/datatables.js";
  import AdminButton from "./AdminButton.svelte";

  type AdminTableLike = {
    currentPage?: number;
    pageCount?: number;
    rowCount?: { total?: number | string | null };
    setPage: (page: number) => void;
  };
  type TableSignal = {
    subscribe: (run: (value: AdminTableLike | null) => void) => () => void;
  };
  type PageItem =
    | { type: "ellipsis"; key: string }
    | { type: "page"; key: string; index: number; label: number };

  export let meta = "";
  export let prevLabel = "Back";
  export let nextLabel = "Next";
  export let table: AdminTableLike | null = null;
  export let page: number | null = null;
  export let pageCount: number | null = null;
  export let total: number | string | null = null;
  export let pageLabel = "Page";
  export let ofLabel = "of";
  export let totalLabel = "Total";
  export let jumpLabel = "Page";
  export let jumpAriaLabel = "Go to page";
  export let goLabel = "Go";
  export let disabled = false;
  export let prevDisabled = false;
  export let nextDisabled = false;
  export let onPrev: () => void = () => {};
  export let onNext: () => void = () => {};
  export let onPageChange: ((page: number) => void) | null = null;

  let jumpValue = "";

  // Bridge the runes-based handler into a store so paging re-renders this
  // legacy component (direct reads of table.* are untracked by Svelte).
  $: tableSignal = watchAdminDatatable(table) as TableSignal;
  $: liveTable = $tableSignal;
  $: tablePage = liveTable ? Number(liveTable.currentPage || 1) - 1 : null;
  $: tablePageCount = liveTable ? Number(liveTable.pageCount || 0) : null;
  $: tableTotal = liveTable ? liveTable.rowCount?.total : total;
  $: normalizedPage = Number(table ? tablePage : page);
  $: normalizedPageCount = Math.max(1, Math.ceil(Number(table ? tablePageCount : pageCount) || 1));
  $: hasPageNavigation =
    Number.isFinite(normalizedPage) && (table || typeof onPageChange === "function");
  $: currentPage = hasPageNavigation
    ? Math.min(Math.max(0, Math.floor(normalizedPage)), normalizedPageCount - 1)
    : 0;
  $: pages = hasPageNavigation ? visiblePages(currentPage, normalizedPageCount) : [];
  $: paginationDisabled = Boolean(disabled);
  $: computedPrevDisabled =
    paginationDisabled || prevDisabled || (hasPageNavigation ? currentPage <= 0 : false);
  $: computedNextDisabled =
    paginationDisabled ||
    nextDisabled ||
    (hasPageNavigation ? currentPage >= normalizedPageCount - 1 : false);
  $: hasTotal = tableTotal !== null && tableTotal !== undefined && tableTotal !== "";
  $: totalValue = Number(tableTotal);
  $: showTotal = hasTotal && Number.isFinite(totalValue) && totalValue >= 0;
  $: jumpTarget = Number(jumpValue);
  $: canJump =
    hasPageNavigation &&
    !paginationDisabled &&
    jumpValue !== "" &&
    Number.isFinite(jumpTarget) &&
    Number.isInteger(jumpTarget) &&
    jumpTarget >= 1 &&
    jumpTarget <= normalizedPageCount;

  function visiblePages(activePage: number, count: number): PageItem[] {
    const pageIndexes = new Set([0, count - 1, activePage - 1, activePage, activePage + 1]);

    if (activePage <= 2) {
      pageIndexes.add(1);
      pageIndexes.add(2);
    }
    if (activePage >= count - 3) {
      pageIndexes.add(count - 2);
      pageIndexes.add(count - 3);
    }

    const sorted = [...pageIndexes]
      .filter((value) => value >= 0 && value < count)
      .sort((a, b) => a - b);

    const result: PageItem[] = [];
    sorted.forEach((value, index) => {
      const previous = sorted[index - 1];
      if (previous !== undefined && value - previous > 1) {
        result.push({ type: "ellipsis", key: `ellipsis-${previous}-${value}` });
      }
      result.push({ type: "page", key: `page-${value}`, index: value, label: value + 1 });
    });
    return result;
  }

  function goToPage(nextPage: number) {
    if (!hasPageNavigation || paginationDisabled) return;
    const clamped = Math.min(
      Math.max(0, Math.floor(Number(nextPage) || 0)),
      normalizedPageCount - 1
    );
    if (clamped === currentPage) return;
    if (table) table.setPage(clamped + 1);
    if (typeof onPageChange === "function") onPageChange(clamped);
  }

  function handlePrev() {
    if (computedPrevDisabled) return;
    if (hasPageNavigation) goToPage(currentPage - 1);
    else onPrev();
  }

  function handleNext() {
    if (computedNextDisabled) return;
    if (hasPageNavigation) goToPage(currentPage + 1);
    else onNext();
  }

  function submitJump() {
    if (!canJump) return;
    goToPage(jumpTarget - 1);
    jumpValue = "";
  }
</script>

<div class="admin-pagination">
  <div class="admin-pagination-summary">
    {#if meta}
      <span class="admin-pagination-meta">{meta}</span>
    {/if}
    {#if hasPageNavigation}
      <span class="admin-pagination-count">
        {pageLabel}
        {currentPage + 1}
        {ofLabel}
        {normalizedPageCount}
      </span>
    {/if}
    {#if showTotal}
      <span class="admin-pagination-count">{totalLabel} {totalValue}</span>
    {/if}
  </div>
  <div class="admin-pagination-buttons">
    <AdminButton
      class="admin-pagination-nav"
      size="sm"
      disabled={computedPrevDisabled}
      onclick={handlePrev}
    >
      <ChevronLeft size={14} />
      {prevLabel}
    </AdminButton>
    {#if hasPageNavigation}
      <div class="admin-pagination-pages" aria-label={pageLabel}>
        {#each pages as item (item.key)}
          {#if item.type === "ellipsis"}
            <span class="admin-pagination-ellipsis" aria-hidden="true">...</span>
          {:else}
            <AdminButton
              class={item.index === currentPage
                ? "admin-pagination-page is-active"
                : "admin-pagination-page"}
              size="sm"
              disabled={paginationDisabled}
              aria-current={item.index === currentPage ? "page" : undefined}
              aria-label={`${pageLabel} ${item.label}`}
              onclick={() => goToPage(item.index)}
            >
              {item.label}
            </AdminButton>
          {/if}
        {/each}
      </div>
    {/if}
    <AdminButton
      class="admin-pagination-nav"
      size="sm"
      disabled={computedNextDisabled}
      onclick={handleNext}
    >
      {nextLabel}
      <ChevronRight size={14} />
    </AdminButton>
  </div>
  {#if hasPageNavigation}
    <form class="admin-pagination-jump" on:submit|preventDefault={submitJump}>
      <label class="admin-pagination-jump-label">
        <span>{jumpLabel}</span>
        <input
          class="admin-pagination-jump-input"
          type="number"
          min="1"
          max={normalizedPageCount}
          step="1"
          inputmode="numeric"
          aria-label={jumpAriaLabel}
          placeholder={String(currentPage + 1)}
          value={jumpValue}
          on:input={(event) => (jumpValue = event.currentTarget.value)}
          disabled={paginationDisabled}
        />
      </label>
      <AdminButton
        class="admin-pagination-jump-button"
        size="sm"
        type="submit"
        disabled={!canJump}
        aria-label={goLabel}
        title={goLabel}
      >
        <ArrowRight size={13} />
      </AdminButton>
    </form>
  {/if}
</div>

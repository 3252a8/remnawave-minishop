<script lang="ts">
  import { ArrowRight, ChevronLeft, ChevronRight } from "$components/ui/icons.js";
  import AdminButton from "./AdminButton.svelte";
  import Input from "$components/ui/input.svelte";

  type AdminTableLike = {
    currentPage?: number;
    pageCount?: number;
    rowCount?: { total?: number | string | null };
    setPage: (page: number) => void;
  };
  type PageItem =
    { type: "ellipsis"; key: string } | { type: "page"; key: string; index: number; label: number };

  let {
    meta = "",
    prevLabel = "Back",
    nextLabel = "Next",
    table = null,
    page = null,
    pageCount = null,
    total = null,
    pageLabel = "Page",
    ofLabel = "of",
    totalLabel = "Total",
    jumpLabel = "Page",
    jumpAriaLabel = "Go to page",
    goLabel = "Go",
    disabled = false,
    prevDisabled = false,
    nextDisabled = false,
    onPrev = () => {},
    onNext = () => {},
    onPageChange = null,
  }: {
    meta?: string;
    prevLabel?: string;
    nextLabel?: string;
    table?: AdminTableLike | null;
    page?: number | null;
    pageCount?: number | null;
    total?: number | string | null;
    pageLabel?: string;
    ofLabel?: string;
    totalLabel?: string;
    jumpLabel?: string;
    jumpAriaLabel?: string;
    goLabel?: string;
    disabled?: boolean;
    prevDisabled?: boolean;
    nextDisabled?: boolean;
    onPrev?: () => void;
    onNext?: () => void;
    onPageChange?: ((page: number) => void) | null;
  } = $props();

  let jumpValue = $state("");

  const liveTable = $derived(table);
  const tablePage = $derived(liveTable ? Number(liveTable.currentPage || 1) - 1 : null);
  const tablePageCount = $derived(liveTable ? Number(liveTable.pageCount || 0) : null);
  const tableTotal = $derived(liveTable ? liveTable.rowCount?.total : total);
  const normalizedPage = $derived(Number(table ? tablePage : page));
  const normalizedPageCount = $derived(
    Math.max(1, Math.ceil(Number(table ? tablePageCount : pageCount) || 1))
  );
  const hasPageNavigation = $derived(
    Number.isFinite(normalizedPage) && (table || typeof onPageChange === "function")
  );
  const currentPage = $derived(
    hasPageNavigation
      ? Math.min(Math.max(0, Math.floor(normalizedPage)), normalizedPageCount - 1)
      : 0
  );
  const pages = $derived(hasPageNavigation ? visiblePages(currentPage, normalizedPageCount) : []);
  const paginationDisabled = $derived(Boolean(disabled));
  const computedPrevDisabled = $derived(
    paginationDisabled || prevDisabled || (hasPageNavigation ? currentPage <= 0 : false)
  );
  const computedNextDisabled = $derived(
    paginationDisabled ||
      nextDisabled ||
      (hasPageNavigation ? currentPage >= normalizedPageCount - 1 : false)
  );
  const hasTotal = $derived(tableTotal !== null && tableTotal !== undefined && tableTotal !== "");
  const totalValue = $derived(Number(tableTotal));
  const showTotal = $derived(hasTotal && Number.isFinite(totalValue) && totalValue >= 0);
  const jumpTarget = $derived(Number(jumpValue));
  const canJump = $derived(
    hasPageNavigation &&
      !paginationDisabled &&
      jumpValue !== "" &&
      Number.isFinite(jumpTarget) &&
      Number.isInteger(jumpTarget) &&
      jumpTarget >= 1 &&
      jumpTarget <= normalizedPageCount
  );

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
    <form
      class="admin-pagination-jump"
      onsubmit={(event) => {
        event.preventDefault();
        submitJump();
      }}
    >
      <label class="admin-pagination-jump-label">
        <span>{jumpLabel}</span>
        <Input
          name="admin-pagination-jump"
          class="admin-pagination-jump-input"
          type="number"
          min="1"
          max={normalizedPageCount}
          step="1"
          inputmode="numeric"
          aria-label={jumpAriaLabel}
          placeholder={String(currentPage + 1)}
          value={jumpValue}
          oninput={(event) => (jumpValue = event.currentTarget.value)}
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

<script lang="ts" generics="TRow">
  import { onDestroy, onMount, tick, type Snippet } from "svelte";
  import { calculateVirtualRange } from "$lib/admin/virtualRows";

  type RowKey = string | number;

  let {
    rows = [],
    children,
    colspan = 1,
    getKey = (_row: TRow, index: number) => index,
    overscan = 6,
    rowHeight = 56,
    threshold = 80,
  }: {
    rows?: readonly TRow[];
    children: Snippet<[TRow, number]>;
    colspan?: number;
    getKey?: (row: TRow, index: number) => RowKey;
    overscan?: number;
    rowHeight?: number;
    threshold?: number;
  } = $props();

  let bodyElement = $state<HTMLTableSectionElement | null>(null);
  let rangeStart = $state(0);
  let rangeEnd = $state(0);
  let frame = 0;
  let scrollTarget: HTMLElement | Window | null = null;
  let disposed = false;

  const rowCount = $derived(rows.length);
  const useVirtual = $derived(rowCount > threshold);
  const visibleRows = $derived(
    useVirtual
      ? rows.slice(rangeStart, rangeEnd).map((row, offset) => ({
          index: rangeStart + offset,
          row,
        }))
      : rows.map((row, index) => ({ index, row }))
  );
  const beforeHeight = $derived(useVirtual ? rangeStart * rowHeight : 0);
  const afterHeight = $derived(useVirtual ? Math.max(0, rowCount - rangeEnd) * rowHeight : 0);

  function scrollContainerFor(element: HTMLElement): HTMLElement | Window {
    let current = element.parentElement;
    while (current) {
      const overflowY = getComputedStyle(current).overflowY;
      if (/(auto|scroll|overlay)/.test(overflowY)) return current;
      current = current.parentElement;
    }
    return window;
  }

  function viewportHeight(): number {
    if (!(scrollTarget instanceof HTMLElement)) return window.innerHeight;
    return scrollTarget.getBoundingClientRect().height;
  }

  function offsetTopInViewport(): number {
    if (!bodyElement) return 0;
    const rect = bodyElement.getBoundingClientRect();
    if (!(scrollTarget instanceof HTMLElement)) return rect.top;
    return rect.top - scrollTarget.getBoundingClientRect().top;
  }

  function updateRange(): void {
    if (disposed) return;
    const nextRowCount = rows.length;
    const shouldVirtualize = nextRowCount > threshold;
    if (!shouldVirtualize || !bodyElement || typeof window === "undefined") {
      rangeStart = 0;
      rangeEnd = nextRowCount;
      return;
    }
    const next = calculateVirtualRange({
      rowCount: nextRowCount,
      rowHeight,
      viewportHeight: viewportHeight(),
      offsetTop: offsetTopInViewport(),
      overscan,
    });
    rangeStart = next.start;
    rangeEnd = next.end;
  }

  function scheduleRangeUpdate(): void {
    if (typeof window === "undefined") return;
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      updateRange();
    });
  }

  $effect(() => {
    rows.length;
    threshold;
    void tick().then(() => {
      updateRange();
    });
  });

  onMount(() => {
    disposed = false;
    if (bodyElement) scrollTarget = scrollContainerFor(bodyElement);
    updateRange();
    scrollTarget?.addEventListener("scroll", scheduleRangeUpdate, { passive: true });
    window.addEventListener("resize", scheduleRangeUpdate);
    return () => {
      disposed = true;
      scrollTarget?.removeEventListener("scroll", scheduleRangeUpdate);
      window.removeEventListener("resize", scheduleRangeUpdate);
      if (frame) window.cancelAnimationFrame(frame);
    };
  });

  onDestroy(() => {
    disposed = true;
    if (frame && typeof window !== "undefined") window.cancelAnimationFrame(frame);
  });
</script>

<tbody bind:this={bodyElement}>
  {#if beforeHeight}
    <tr class="admin-virtual-spacer" aria-hidden="true">
      <td colspan={Math.max(1, colspan)} style:height={`${beforeHeight}px`}></td>
    </tr>
  {/if}

  {#each visibleRows as item (getKey(item.row, item.index))}
    {@render children(item.row, item.index)}
  {/each}

  {#if afterHeight}
    <tr class="admin-virtual-spacer" aria-hidden="true">
      <td colspan={Math.max(1, colspan)} style:height={`${afterHeight}px`}></td>
    </tr>
  {/if}
</tbody>

<style>
  .admin-virtual-spacer td {
    padding: 0 !important;
    border: 0 !important;
    pointer-events: none;
  }
</style>

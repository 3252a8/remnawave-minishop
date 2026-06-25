<script>
  import { draggable } from "@neodrag/svelte";
  import { flip } from "svelte/animate";
  import { cubicOut } from "svelte/easing";
  import { cn } from "$lib/utils.js";
  import { GripVertical } from "./icons.js";

  // Reusable drag-to-reorder list. bits-ui / shadcn-svelte have no sortable
  // primitive, so this layers @neodrag pointer gestures over a grip handle.
  // Each item is rendered through the default (scoped) slot, which receives
  // `item`, `index` and `dragging`. The slot content fills the row alongside
  // the leading drag handle, so pass a grid `class` whose first column matches
  // the handle width.
  let {
    items = [],
    onReorder = () => {},
    getKey = (item) => item,
    handleLabel = "Drag to reorder",
    disabled = false,
    class: className = "",
    containerClass = "",
    children,
  } = $props();

  let containerEl = $state();
  let dragIndex = $state(null);
  let dropSlot = $state(null);
  let dropIndex = $state(null);
  let dragResetToken = $state(0);
  let rowRects = $state([]);
  const dragActive = $derived(dragIndex !== null);
  const dragDisabled = $derived(disabled || !items?.length || items.length < 2);

  const flipConfig = {
    duration(distance) {
      if (
        typeof window !== "undefined" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ) {
        return 0;
      }
      return Math.min(220, 110 + distance * 0.35);
    },
    easing: cubicOut,
  };

  function dragOptions(index) {
    return {
      axis: "y",
      disabled: dragDisabled,
      position: dragActive ? undefined : { x: 0, y: 0 },
      threshold: { distance: 5 },
      defaultClass: "ui-sortable-neodrag",
      defaultClassDragging: "ui-sortable-neodragging",
      defaultClassDragged: "ui-sortable-neodragged",
      transform: ({ offsetY, rootNode }) => {
        const row = rowForNode(rootNode);
        if (!row) return;
        row.style.transform =
          dragIndex === index ? `translate3d(0, ${offsetY}px, 0) scale(0.992)` : "";
      },
      onDragStart: (data) => startPointerDrag(index, data),
      onDrag: updatePointerDrag,
      onDragEnd: finishPointerDrag,
    };
  }

  function snapshotRows() {
    rowRects = Array.from(containerEl?.querySelectorAll(".ui-sortable-item") || []).map(
      (node, index) => {
        const rect = node.getBoundingClientRect();
        return {
          index,
          midY: rect.top + rect.height / 2,
        };
      }
    );
  }

  function slotFromPointer(clientY) {
    if (!rowRects.length) return dragIndex ?? 0;
    const target = rowRects.find((row) => clientY < row.midY);
    return target ? target.index : rowRects.length;
  }

  function targetIndexFromSlot(slot) {
    if (dragIndex === null || !rowRects.length) return null;
    const nextIndex = slot > dragIndex ? slot - 1 : slot;
    return Math.min(Math.max(nextIndex, 0), rowRects.length - 1);
  }

  function updateDropTarget(clientY) {
    const nextSlot = slotFromPointer(clientY);
    const nextIndex = targetIndexFromSlot(nextSlot);
    if (dropSlot !== nextSlot) dropSlot = nextSlot;
    if (dropIndex !== nextIndex) dropIndex = nextIndex;
  }

  function startPointerDrag(index, data) {
    if (dragDisabled) return;
    dragIndex = index;
    dropSlot = index;
    dropIndex = index;
    snapshotRows();
    updateDropTarget(data.event.clientY);
    const row = rowForNode(data.rootNode);
    if (row) row.style.zIndex = "2";
  }

  function updatePointerDrag(data) {
    if (dragIndex === null) return;
    updateDropTarget(data.event.clientY);
  }

  function rowForNode(node) {
    return node?.closest?.(".ui-sortable-item") || null;
  }

  function clearDraggedNode(node) {
    const row = rowForNode(node);
    if (!row) return;
    row.style.transform = "";
    row.style.zIndex = "";
  }

  function finishPointerDrag(data) {
    const from = dragIndex;
    const to = dropIndex;
    clearDraggedNode(data.rootNode);
    const shouldReorder = !dragDisabled && from !== null && to !== null && from !== to;
    reset({ remount: true });
    if (shouldReorder) {
      onReorder(from, to);
    }
  }

  function handleHandleKeydown(event, index) {
    if (dragDisabled) return;
    const direction = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0;
    if (!direction) return;
    event.preventDefault();
    const nextIndex = Math.min(Math.max(0, index + direction), items.length - 1);
    if (nextIndex !== index) onReorder(index, nextIndex);
  }

  function reset({ remount = false } = {}) {
    dragIndex = null;
    dropSlot = null;
    dropIndex = null;
    rowRects = [];
    if (remount) dragResetToken += 1;
  }

  function cancelPointerDrag(event) {
    clearDraggedNode(event.currentTarget);
    reset({ remount: true });
  }

  function isDropSlot(index) {
    if (dragIndex === null || dropIndex === null || dropIndex === dragIndex) return false;
    return dropSlot === index || (dropSlot === items.length && index === items.length - 1);
  }

  function isDropAfter(index) {
    return isDropSlot(index) && dropSlot === items.length && index === items.length - 1;
  }
</script>

<div
  bind:this={containerEl}
  class={cn("ui-sortable", containerClass)}
  class:is-drag-active={dragActive}
  role="list"
>
  {#each items as item, index (getKey(item, index))}
    <div
      class={cn("ui-sortable-item", className)}
      class:is-dragging={dragIndex === index}
      class:is-drop-target={isDropSlot(index)}
      class:is-drop-after={isDropAfter(index)}
      role="listitem"
      animate:flip={flipConfig}
    >
      {#key dragResetToken}
        <button
          use:draggable={dragOptions(index)}
          type="button"
          class="ui-sortable-handle"
          disabled={dragDisabled}
          aria-label={handleLabel}
          aria-grabbed={dragIndex === index}
          title={handleLabel}
          onpointercancel={cancelPointerDrag}
          onkeydown={(event) => handleHandleKeydown(event, index)}
        >
          <GripVertical size={14} />
        </button>
      {/key}
      {@render children?.(item, index, dragIndex === index)}
    </div>
  {/each}
</div>

<style>
  .ui-sortable {
    --sortable-accent: var(--admin-ring, var(--admin-accent, var(--accent, #4f8cff)));
    --sortable-drop-soft: color-mix(in srgb, var(--sortable-accent) 10%, transparent);
    --sortable-drop-line: color-mix(
      in srgb,
      var(--sortable-accent) 78%,
      var(--admin-text, #ffffff)
    );
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .ui-sortable-item {
    position: relative;
    min-width: 0;
    border-radius: 8px;
    transition:
      background-color 160ms ease,
      box-shadow 160ms ease,
      opacity 160ms ease,
      transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  .ui-sortable.is-drag-active {
    user-select: none;
    -webkit-user-select: none;
  }

  .ui-sortable.is-drag-active :global(input),
  .ui-sortable.is-drag-active :global(textarea),
  .ui-sortable.is-drag-active :global(select) {
    pointer-events: none;
  }

  .ui-sortable.is-drag-active .ui-sortable-item {
    transition:
      background-color 120ms ease,
      box-shadow 120ms ease,
      opacity 120ms ease;
  }

  .ui-sortable-item.is-dragging {
    opacity: 0.46;
    transform: scale(0.992);
  }

  .ui-sortable-item.is-drop-target {
    background: var(--sortable-drop-soft);
    box-shadow:
      inset 0 0 0 1px color-mix(in srgb, var(--sortable-accent) 38%, transparent),
      0 8px 24px color-mix(in srgb, var(--sortable-accent) 8%, transparent);
    transform: translateY(-1px);
  }

  .ui-sortable-item.is-drop-target::before {
    content: "";
    position: absolute;
    top: -6px;
    left: 0;
    right: 0;
    z-index: 1;
    height: 3px;
    border-radius: 999px;
    background: var(--sortable-drop-line);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--sortable-accent) 16%, transparent);
    pointer-events: none;
  }

  .ui-sortable-item.is-drop-after::before {
    top: auto;
    bottom: -6px;
  }

  .ui-sortable-handle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 100%;
    padding: 0;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--admin-muted, inherit);
    cursor: grab;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    transition:
      background-color 160ms ease,
      color 160ms ease,
      transform 160ms ease,
      box-shadow 160ms ease;
  }

  .ui-sortable-handle :global(svg) {
    pointer-events: none;
  }

  .ui-sortable-handle:hover {
    background: color-mix(in srgb, var(--sortable-accent) 10%, transparent);
    color: var(--admin-text, inherit);
  }

  .ui-sortable-handle:focus-visible {
    outline: none;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--sortable-accent) 22%, transparent);
    color: var(--admin-text, inherit);
  }

  .ui-sortable-handle:active {
    cursor: grabbing;
    transform: scale(0.94);
  }

  .ui-sortable.is-drag-active .ui-sortable-handle {
    cursor: grabbing;
  }

  .ui-sortable-handle:disabled {
    cursor: default;
    opacity: 0.5;
  }

  @media (prefers-reduced-motion: reduce) {
    .ui-sortable-item,
    .ui-sortable-handle {
      transition: none;
    }

    .ui-sortable-item.is-dragging,
    .ui-sortable-item.is-drop-target,
    .ui-sortable-handle:active {
      transform: none;
    }
  }
</style>

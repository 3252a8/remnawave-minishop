<script>
  import { flip } from "svelte/animate";
  import { cubicOut } from "svelte/easing";
  import { cn } from "$lib/utils.js";
  import { GripVertical } from "./icons.js";

  // Reusable drag-to-reorder list. bits-ui / shadcn-svelte have no sortable
  // primitive, so this wraps native HTML5 drag & drop with a grip handle.
  // Each item is rendered through the default (scoped) slot, which receives
  // `item`, `index` and `dragging`. The slot content fills the row alongside
  // the leading drag handle, so pass a grid `class` whose first column matches
  // the handle width.
  export let items = [];
  export let onReorder = () => {};
  export let getKey = (item) => item;
  export let handleLabel = "Drag to reorder";
  export let disabled = false;
  let className = "";
  export { className as class };
  export let containerClass = "";

  let dragIndex = null;
  let dropIndex = null;
  $: dragActive = dragIndex !== null;

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

  function handleDragStart(event, index) {
    if (disabled) {
      event.preventDefault();
      return;
    }
    dragIndex = index;
    dropIndex = index;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      // Firefox requires data to be set for a drag to start.
      event.dataTransfer.setData("text/plain", String(index));
      const dragRow = event.currentTarget?.closest?.(".ui-sortable-item");
      if (dragRow) {
        const rect = dragRow.getBoundingClientRect();
        event.dataTransfer.setDragImage(dragRow, 18, rect.height / 2);
      }
    }
  }

  function handleDragOver(event, index) {
    if (dragIndex === null) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    if (dropIndex !== index) dropIndex = index;
  }

  function handleDrop(event, index) {
    if (dragIndex === null) return;
    event.preventDefault();
    if (dragIndex !== index) onReorder(dragIndex, index);
    dragIndex = null;
    dropIndex = null;
  }

  function reset() {
    dragIndex = null;
    dropIndex = null;
  }
</script>

<div class={cn("ui-sortable", containerClass)} class:is-drag-active={dragActive} role="list">
  {#each items as item, index (getKey(item, index))}
    <div
      class={cn("ui-sortable-item", className)}
      class:is-dragging={dragIndex === index}
      class:is-drop-target={dropIndex === index && dragIndex !== index}
      role="listitem"
      animate:flip={flipConfig}
      on:dragover={(event) => handleDragOver(event, index)}
      on:drop={(event) => handleDrop(event, index)}
      on:dragend={reset}
    >
      <button
        type="button"
        class="ui-sortable-handle"
        draggable={!disabled}
        {disabled}
        aria-label={handleLabel}
        aria-grabbed={dragIndex === index}
        title={handleLabel}
        on:dragstart={(event) => handleDragStart(event, index)}
      >
        <GripVertical size={14} />
      </button>
      <slot {item} {index} dragging={dragIndex === index} />
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
    transition:
      background-color 160ms ease,
      color 160ms ease,
      transform 160ms ease,
      box-shadow 160ms ease;
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

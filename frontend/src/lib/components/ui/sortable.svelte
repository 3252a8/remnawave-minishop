<script>
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

  function handleDragStart(event, index) {
    if (disabled) return;
    dragIndex = index;
    dropIndex = index;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      // Firefox requires data to be set for a drag to start.
      event.dataTransfer.setData("text/plain", String(index));
    }
  }

  function handleDragOver(event, index) {
    if (dragIndex === null) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    dropIndex = index;
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

<div class={cn("ui-sortable", containerClass)} role="list">
  {#each items as item, index (getKey(item, index))}
    <div
      class={cn("ui-sortable-item", className)}
      class:is-dragging={dragIndex === index}
      class:is-drop-target={dropIndex === index && dragIndex !== index}
      role="listitem"
      on:dragover={(event) => handleDragOver(event, index)}
      on:drop={(event) => handleDrop(event, index)}
      on:dragend={reset}
    >
      <button
        type="button"
        class="ui-sortable-handle"
        draggable={!disabled}
        aria-label={handleLabel}
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
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .ui-sortable-item.is-dragging {
    opacity: 0.5;
  }

  .ui-sortable-item.is-drop-target {
    outline: 2px dashed var(--admin-accent, #4f8cff);
    outline-offset: 2px;
    border-radius: 8px;
  }

  .ui-sortable-handle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--admin-muted, inherit);
    cursor: grab;
    touch-action: none;
  }

  .ui-sortable-handle:hover {
    color: var(--admin-text, inherit);
  }

  .ui-sortable-handle:active {
    cursor: grabbing;
  }
</style>

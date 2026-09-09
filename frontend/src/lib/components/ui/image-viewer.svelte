<script lang="ts">
  import { Minus, Plus, RotateCcw, X } from "$components/ui/icons.js";
  import {
    focusFirstDialogControl,
    handleDialogFocusTrap,
  } from "$lib/components/dialogFocusTrap.js";
  import { lockPageScroll } from "$lib/webapp/scrollLock.js";
  import Button from "./button.svelte";

  type Props = {
    open?: boolean;
    src?: string;
    alt?: string;
    title?: string;
    closeLabel?: string;
    zoomInLabel?: string;
    zoomOutLabel?: string;
    resetLabel?: string;
    onclose?: () => void;
  };

  let {
    open = false,
    src = "",
    alt = "",
    title = "",
    closeLabel = "Close",
    zoomInLabel = "Zoom in",
    zoomOutLabel = "Zoom out",
    resetLabel = "Reset zoom",
    onclose = () => {},
  }: Props = $props();

  const MIN_SCALE = 1;
  const MAX_SCALE = 5;
  const ZOOM_STEP = 0.25;
  const KEYBOARD_PAN_STEP = 36;

  let dialog = $state<HTMLElement | null>(null);
  let scale = $state(MIN_SCALE);
  let panX = $state(0);
  let panY = $state(0);
  let dragging = $state(false);
  let dragPointerId = $state<number | null>(null);
  let dragStartX = $state(0);
  let dragStartY = $state(0);
  let dragOriginX = $state(0);
  let dragOriginY = $state(0);

  const zoomPercent = $derived(Math.round(scale * 100));

  function resetView(): void {
    scale = MIN_SCALE;
    panX = 0;
    panY = 0;
    dragging = false;
    dragPointerId = null;
  }

  function setScale(nextScale: number): void {
    scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
    if (scale === MIN_SCALE) {
      panX = 0;
      panY = 0;
    }
  }

  function handleWheel(event: WheelEvent): void {
    event.preventDefault();
    event.stopPropagation();
    setScale(scale + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
  }

  function handleDoubleClick(): void {
    if (scale > MIN_SCALE) resetView();
    else setScale(2);
  }

  function handlePointerDown(event: PointerEvent): void {
    if (scale <= MIN_SCALE || event.button !== 0) return;
    const element = event.currentTarget as HTMLElement;
    element.setPointerCapture(event.pointerId);
    dragging = true;
    dragPointerId = event.pointerId;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragOriginX = panX;
    dragOriginY = panY;
  }

  function handlePointerMove(event: PointerEvent): void {
    if (!dragging || dragPointerId !== event.pointerId) return;
    panX = dragOriginX + event.clientX - dragStartX;
    panY = dragOriginY + event.clientY - dragStartY;
  }

  function handlePointerEnd(event: PointerEvent): void {
    if (dragPointerId !== event.pointerId) return;
    const element = event.currentTarget as HTMLElement;
    if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
    dragging = false;
    dragPointerId = null;
  }

  function handleKeydown(event: KeyboardEvent): void {
    event.stopPropagation();
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      setScale(scale + ZOOM_STEP);
      return;
    }
    if (event.key === "-") {
      event.preventDefault();
      setScale(scale - ZOOM_STEP);
      return;
    }
    if (event.key === "0") {
      event.preventDefault();
      resetView();
      return;
    }
    if (scale > MIN_SCALE && event.key.startsWith("Arrow")) {
      event.preventDefault();
      if (event.key === "ArrowLeft") panX -= KEYBOARD_PAN_STEP;
      if (event.key === "ArrowRight") panX += KEYBOARD_PAN_STEP;
      if (event.key === "ArrowUp") panY -= KEYBOARD_PAN_STEP;
      if (event.key === "ArrowDown") panY += KEYBOARD_PAN_STEP;
      return;
    }
    handleDialogFocusTrap(event, dialog, onclose);
  }

  $effect(() => {
    if (!open || !src) return;
    resetView();
    focusFirstDialogControl(() => dialog);
    return lockPageScroll();
  });
</script>

{#if open && src}
  <div
    class="image-viewer"
    role="dialog"
    aria-modal="true"
    aria-label={title || alt}
    tabindex="-1"
    data-image-viewer
    onkeydown={handleKeydown}
    onwheel={handleWheel}
  >
    <button class="image-viewer-backdrop" type="button" aria-label={closeLabel} onclick={onclose}
    ></button>
    <section bind:this={dialog} class="image-viewer-panel">
      <header class="image-viewer-toolbar">
        <strong {title}>{title}</strong>
        <div class="image-viewer-controls">
          <Button
            variant="icon"
            size="icon"
            data-image-viewer-action="zoom-out"
            onclick={() => setScale(scale - ZOOM_STEP)}
            disabled={scale <= MIN_SCALE}
            aria-label={zoomOutLabel}
            title={zoomOutLabel}
          >
            <Minus size={18} />
          </Button>
          <span class="image-viewer-scale" aria-live="polite">{zoomPercent}%</span>
          <Button
            variant="icon"
            size="icon"
            data-image-viewer-action="zoom-in"
            onclick={() => setScale(scale + ZOOM_STEP)}
            disabled={scale >= MAX_SCALE}
            aria-label={zoomInLabel}
            title={zoomInLabel}
          >
            <Plus size={18} />
          </Button>
          <Button
            variant="icon"
            size="icon"
            data-image-viewer-action="reset"
            onclick={resetView}
            disabled={scale === MIN_SCALE && panX === 0 && panY === 0}
            aria-label={resetLabel}
            title={resetLabel}
          >
            <RotateCcw size={17} />
          </Button>
          <Button
            variant="icon"
            size="icon"
            data-image-viewer-action="close"
            onclick={onclose}
            aria-label={closeLabel}
            title={closeLabel}
          >
            <X size={19} />
          </Button>
        </div>
      </header>
      <div
        class="image-viewer-stage"
        class:is-zoomed={scale > MIN_SCALE}
        class:is-dragging={dragging}
        role="presentation"
        onpointerdown={handlePointerDown}
        onpointermove={handlePointerMove}
        onpointerup={handlePointerEnd}
        onpointercancel={handlePointerEnd}
        ondblclick={handleDoubleClick}
      >
        <img
          {src}
          {alt}
          draggable="false"
          decoding="async"
          style:transform={`translate3d(${panX}px, ${panY}px, 0) scale(${scale})`}
        />
      </div>
    </section>
  </div>
{/if}

<style>
  .image-viewer {
    box-sizing: border-box;
    position: fixed;
    inset: 0;
    z-index: 1600;
    display: grid;
    place-items: center;
    padding: max(12px, var(--content-safe-area-top)) max(12px, var(--content-safe-area-right))
      max(12px, var(--content-safe-area-bottom)) max(12px, var(--content-safe-area-left));
  }

  .image-viewer-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    background: color-mix(in srgb, #020617 88%, transparent);
    backdrop-filter: blur(10px);
    cursor: zoom-out;
  }

  .image-viewer-panel {
    position: relative;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    width: min(1180px, 100%);
    height: min(900px, 100%);
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.26));
    border-radius: 18px;
    background: color-mix(in srgb, var(--panel, #0b1220) 96%, #020617);
    box-shadow: 0 32px 96px rgba(0, 0, 0, 0.55);
  }

  .image-viewer-toolbar {
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-width: 0;
    padding: 10px 12px 10px 16px;
    border-bottom: 1px solid var(--border, rgba(148, 163, 184, 0.24));
    background: color-mix(in srgb, var(--panel-2, #111827) 94%, transparent);
  }

  .image-viewer-toolbar strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text, #f8fafc);
    font-size: 14px;
  }

  .image-viewer-controls {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    gap: 4px;
  }

  .image-viewer-scale {
    min-width: 50px;
    color: var(--muted, #94a3b8);
    font-variant-numeric: tabular-nums;
    text-align: center;
    font-size: 12px;
  }

  .image-viewer-stage {
    display: grid;
    place-items: center;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    touch-action: none;
    user-select: none;
  }

  .image-viewer-stage.is-zoomed {
    cursor: grab;
  }

  .image-viewer-stage.is-dragging {
    cursor: grabbing;
  }

  .image-viewer-stage img {
    display: block;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transform-origin: center;
    transition: transform 120ms ease-out;
    will-change: transform;
  }

  .image-viewer-stage.is-dragging img {
    transition: none;
  }

  @media (max-width: 640px) {
    .image-viewer {
      padding: var(--content-safe-area-top) var(--content-safe-area-right)
        var(--content-safe-area-bottom) var(--content-safe-area-left);
    }

    .image-viewer-panel {
      width: 100%;
      height: 100%;
      border: 0;
      border-radius: 0;
    }

    .image-viewer-toolbar {
      align-items: flex-start;
    }

    .image-viewer-toolbar strong {
      display: none;
    }

    .image-viewer-controls {
      width: 100%;
      justify-content: flex-end;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .image-viewer-stage img {
      transition: none;
    }
  }
</style>

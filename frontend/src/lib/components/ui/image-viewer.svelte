<script lang="ts">
  import { Minus, Plus, RotateCcw, X } from "$components/ui/icons.js";
  import { handleDialogFocusTrap } from "$lib/components/dialogFocusTrap.js";
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
  const STANDARD_MAX_SCALE = 5;
  const ZOOM_STEP = 0.25;
  const KEYBOARD_PAN_STEP = 36;

  let stageWidth = $state(0);
  let stageHeight = $state(0);
  let imageWidth = $state(0);
  let imageHeight = $state(0);
  let naturalWidth = $state(0);
  let naturalHeight = $state(0);
  let scale = $state(MIN_SCALE);
  let panX = $state(0);
  let panY = $state(0);
  type Point = { x: number; y: number };
  let pointers: { id: number; point: Point }[] = [];
  let dragging = $state(false);

  function boundedPan(value: number, imageSize: number, stageSize: number): number {
    const limit = Math.max(0, (imageSize * scale - stageSize) / 2);
    return Math.max(-limit, Math.min(limit, value));
  }

  const zoomPercent = $derived(Math.round(scale * 100));
  // Use the longer fitted edge for accuracy with very tall or narrow screenshots.
  const nativeScale = $derived(
    Math.max(naturalWidth, naturalHeight) / (Math.max(imageWidth, imageHeight) || 1)
  );
  const maxScale = $derived(Math.max(STANDARD_MAX_SCALE, nativeScale));
  const offsetX = $derived(boundedPan(panX, imageWidth, stageWidth));
  const offsetY = $derived(boundedPan(panY, imageHeight, stageHeight));

  function resetView(): void {
    scale = MIN_SCALE;
    panX = 0;
    panY = 0;
    dragging = false;
    pointers = [];
  }

  function setScale(nextScale: number, from: Point = { x: 0, y: 0 }, to = from): void {
    const previousScale = scale;
    const x = offsetX;
    const y = offsetY;
    scale = Math.min(maxScale, Math.max(MIN_SCALE, nextScale));
    // Keep the content under the cursor or the midpoint of a pinch in place.
    panX = boundedPan(to.x + (x - from.x) * (scale / previousScale), imageWidth, stageWidth);
    panY = boundedPan(to.y + (y - from.y) * (scale / previousScale), imageHeight, stageHeight);
  }

  function stagePoint(event: MouseEvent): Point {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return {
      x: event.clientX - rect.x - rect.width / 2,
      y: event.clientY - rect.y - rect.height / 2,
    };
  }

  function handleWheel(event: WheelEvent): void {
    event.preventDefault();
    event.stopPropagation();
    if (event.deltaY)
      setScale(scale + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP), stagePoint(event));
  }

  function handleDoubleClick(event: MouseEvent): void {
    if (scale > MIN_SCALE) resetView();
    else setScale(nativeScale > STANDARD_MAX_SCALE ? nativeScale : 2, stagePoint(event));
  }

  function handlePointerDown(event: PointerEvent): void {
    if (event.button !== 0 || pointers.length >= 2) return;
    const element = event.currentTarget as HTMLElement;
    element.setPointerCapture(event.pointerId);
    pointers.push({ id: event.pointerId, point: stagePoint(event) });
    dragging = scale > MIN_SCALE || pointers.length === 2;
  }

  function handlePointerMove(event: PointerEvent): void {
    const pointer = pointers.find((item) => item.id === event.pointerId);
    if (!pointer) return;
    const previous = pointer.point;
    const next = stagePoint(event);
    pointer.point = next;
    const other = pointers.find((item) => item !== pointer)?.point;
    if (other) {
      const distance = Math.hypot(previous.x - other.x, previous.y - other.y);
      if (distance > 0) {
        setScale(
          (scale * Math.hypot(next.x - other.x, next.y - other.y)) / distance,
          { x: (previous.x + other.x) / 2, y: (previous.y + other.y) / 2 },
          { x: (next.x + other.x) / 2, y: (next.y + other.y) / 2 }
        );
      }
    } else {
      panX = boundedPan(offsetX + next.x - previous.x, imageWidth, stageWidth);
      panY = boundedPan(offsetY + next.y - previous.y, imageHeight, stageHeight);
    }
  }

  function handlePointerEnd(event: PointerEvent): void {
    pointers = pointers.filter((item) => item.id !== event.pointerId);
    dragging = pointers.length > 0 && scale > MIN_SCALE;
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
      if (event.key === "ArrowLeft") panX = offsetX + KEYBOARD_PAN_STEP;
      if (event.key === "ArrowRight") panX = offsetX - KEYBOARD_PAN_STEP;
      if (event.key === "ArrowUp") panY = offsetY + KEYBOARD_PAN_STEP;
      if (event.key === "ArrowDown") panY = offsetY - KEYBOARD_PAN_STEP;
      return;
    }
    const viewer = event.currentTarget as HTMLDialogElement;
    handleDialogFocusTrap(event, viewer.querySelector("section"), onclose);
  }

  function showViewer(element: HTMLDialogElement): () => void {
    const opener = document.activeElement;
    resetView();
    const unlock = lockPageScroll();
    // The top layer escapes transformed messages and keeps the originating theme.
    element.showModal();
    element
      .querySelector<HTMLElement>('[data-image-viewer-action="zoom-in"]')
      ?.focus({ preventScroll: true });
    return () => {
      element.close();
      unlock();
      if (opener instanceof HTMLElement && opener.isConnected)
        opener.focus({ preventScroll: true });
    };
  }
</script>

{#if open && src}
  <dialog
    {@attach showViewer}
    class="image-viewer"
    aria-label={title || alt}
    data-image-viewer
    onkeydown={handleKeydown}
    oncancel={(event) => {
      event.preventDefault();
      onclose();
    }}
  >
    <button class="image-viewer-backdrop" type="button" aria-label={closeLabel} onclick={onclose}
    ></button>
    <section class="image-viewer-panel">
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
            disabled={scale >= maxScale}
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
        bind:clientWidth={stageWidth}
        bind:clientHeight={stageHeight}
        role="presentation"
        onwheel={handleWheel}
        onpointerdown={handlePointerDown}
        onpointermove={handlePointerMove}
        onpointerup={handlePointerEnd}
        onlostpointercapture={handlePointerEnd}
        ondblclick={handleDoubleClick}
      >
        <img
          {src}
          {alt}
          draggable="false"
          decoding="async"
          bind:clientWidth={imageWidth}
          bind:clientHeight={imageHeight}
          bind:naturalWidth
          bind:naturalHeight
          style:transform={`translate3d(${offsetX}px, ${offsetY}px, 0) scale(${scale})`}
        />
      </div>
    </section>
  </dialog>
{/if}

<style>
  .image-viewer {
    box-sizing: border-box;
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    border: 0;
    background: transparent;
    color: inherit;
    overflow: hidden;
    overscroll-behavior: contain;
    grid-template: minmax(0, 1fr) / minmax(0, 1fr);
    place-items: center;
    padding: max(12px, var(--content-safe-area-top)) max(12px, var(--content-safe-area-right))
      max(12px, var(--content-safe-area-bottom)) max(12px, var(--content-safe-area-left));
  }

  .image-viewer[open] {
    display: grid;
  }

  .image-viewer::backdrop {
    background: transparent;
  }

  .image-viewer-backdrop {
    position: absolute;
    inset: 0;
    border: 0;
    background: color-mix(in srgb, #020617 92%, transparent);
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
    grid-template: minmax(0, 1fr) / minmax(0, 1fr);
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

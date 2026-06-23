<script lang="ts">
  import { cn } from "$lib/utils.js";
  import { ScrollArea as ScrollAreaPrimitive } from "./primitives.js";

  type ScrollAreaType = "auto" | "always" | "scroll" | "hover";

  export let maxHeight = "100%";
  export let element: HTMLElement | null = null;
  export let type: ScrollAreaType = "auto";
  let className = "";
  export { className as class };
</script>

<ScrollAreaPrimitive.Root
  class={cn("scroll-area scroll-area--mono", className)}
  style={`max-height:${maxHeight};`}
  {type}
  {...$$restProps}
>
  <ScrollAreaPrimitive.Viewport bind:ref={element} class="scroll-area__viewport">
    <slot />
  </ScrollAreaPrimitive.Viewport>
  <ScrollAreaPrimitive.Scrollbar class="scroll-area__scrollbar" orientation="vertical">
    <ScrollAreaPrimitive.Thumb class="scroll-area__thumb" />
  </ScrollAreaPrimitive.Scrollbar>
  <ScrollAreaPrimitive.Scrollbar
    class="scroll-area__scrollbar scroll-area__scrollbar--horizontal"
    orientation="horizontal"
  >
    <ScrollAreaPrimitive.Thumb class="scroll-area__thumb" />
  </ScrollAreaPrimitive.Scrollbar>
  <ScrollAreaPrimitive.Corner class="scroll-area__corner" />
</ScrollAreaPrimitive.Root>

<style>
  :global(.scroll-area) {
    position: relative;
    overflow: hidden;
  }

  :global(.scroll-area--dialog) {
    overflow: visible;
  }

  :global(.scroll-area__viewport) {
    width: 100%;
    height: 100%;
    max-height: inherit;
    border-radius: inherit;
  }

  :global(.scroll-area__scrollbar) {
    z-index: 2;
    display: flex;
    touch-action: none;
    user-select: none;
    padding: 2px;
    transition: background 0.14s ease;
  }

  :global(.scroll-area__scrollbar[data-orientation="vertical"]) {
    width: 10px;
  }

  :global(.scroll-area--dialog .scroll-area__scrollbar[data-orientation="vertical"]) {
    transform: translateX(12px);
  }

  :global(.scroll-area__scrollbar[data-orientation="horizontal"]) {
    flex-direction: column;
    height: 10px;
  }

  :global(.scroll-area__thumb) {
    position: relative;
    flex: 1;
    border-radius: 999px;
    background: color-mix(
      in srgb,
      var(--admin-muted, var(--muted)) 34%,
      var(--admin-border, var(--border))
    );
  }

  :global(.scroll-area__thumb:hover) {
    background: color-mix(
      in srgb,
      var(--admin-muted, var(--muted)) 48%,
      var(--admin-border, var(--border))
    );
  }

  :global(.scroll-area__corner) {
    background: transparent;
  }
</style>

<script lang="ts">
  import { X } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";
  import {
    focusFirstDialogControl,
    handleDialogFocusTrap,
  } from "$lib/components/dialogFocusTrap.js";
  import { lockPageScroll } from "$lib/webapp/scrollLock.js";
  import type { Snippet } from "svelte";
  import { cubicOut } from "svelte/easing";
  import { prefersReducedMotion } from "svelte/motion";
  import { fade, fly } from "svelte/transition";
  import Button from "./button.svelte";
  import ScrollArea from "./scroll-area.svelte";

  type FadeParams = Parameters<typeof fade>[1];
  type FlyParams = Parameters<typeof fly>[1];
  type ScrollType = "auto" | "always" | "scroll" | "hover";

  type Props = {
    open?: boolean;
    title?: string;
    description?: string;
    closeLabel?: string;
    onclose?: () => void;
    class?: string;
    scrollType?: ScrollType;
    titleIcon?: Snippet;
    headerContent?: Snippet;
    children?: Snippet;
  };

  let {
    open = false,
    title = "",
    description = "",
    closeLabel = "Close",
    onclose = () => {},
    class: className = "",
    scrollType = "auto",
    titleIcon,
    headerContent,
    children,
  }: Props = $props();

  function backdropTransition(): FadeParams {
    return prefersReducedMotion.current ? { duration: 0 } : { duration: 200 };
  }

  function cardIn(): FlyParams {
    return prefersReducedMotion.current
      ? { duration: 0, y: 0 }
      : { duration: 260, y: 16, easing: cubicOut };
  }

  function cardOut(): FlyParams {
    return prefersReducedMotion.current
      ? { duration: 0, y: 0 }
      : { duration: 200, y: 10, easing: cubicOut };
  }

  let overlay = $state<HTMLDivElement | null>(null);
  let card = $state<HTMLElement | null>(null);

  // Escape and Tab are handled on the overlay, not on `window`: a dialog opened
  // from another dialog keeps its own trap, and only the one holding focus
  // reacts to the key.
  function handleKeydown(event: KeyboardEvent) {
    handleDialogFocusTrap(event, card, onclose);
  }

  $effect(() => {
    if (!open) return;
    focusFirstDialogControl(() => card);
  });

  function stopScrollPropagation(event: WheelEvent | TouchEvent) {
    event.stopPropagation();
    if (event.target instanceof Element && event.target.closest(".dialog-body-scroll")) return;
    event.preventDefault();
  }

  $effect(() => {
    if (!open) return;
    return lockPageScroll();
  });

  // Svelte attaches `touchmove` passively, where `preventDefault()` is ignored,
  // so the guard that keeps a drag on the backdrop from scrolling the page is
  // registered by hand. Wheel stays on the markup: it is cancelable there.
  $effect(() => {
    const element = overlay;
    if (!open || !element) return;
    element.addEventListener("touchmove", stopScrollPropagation, { passive: false });
    return () => element.removeEventListener("touchmove", stopScrollPropagation);
  });
</script>

{#if open}
  <div
    bind:this={overlay}
    class="dialog"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
    onwheel={stopScrollPropagation}
    onkeydown={handleKeydown}
  >
    <button
      class="dialog-backdrop"
      type="button"
      aria-label={closeLabel}
      onclick={onclose}
      in:fade={backdropTransition()}
      out:fade={backdropTransition()}
    ></button>
    <section
      bind:this={card}
      class={cn("dialog-card", className)}
      in:fly={cardIn()}
      out:fly={cardOut()}
    >
      <div class:dialog-head-custom={headerContent} class="dialog-head">
        <div class:dialog-title-with-icon={titleIcon} class="dialog-title-block">
          {#if headerContent}
            {@render headerContent()}
          {:else}
            {#if titleIcon}
              <span class="dialog-title-icon" aria-hidden="true">
                {@render titleIcon()}
              </span>
            {/if}
            <div class="dialog-title-copy">
              {#if title}<h2>{title}</h2>{/if}
              {#if description}<p>{description}</p>{/if}
            </div>
          {/if}
        </div>
        <Button
          class="dialog-close-button"
          variant="icon"
          size="icon"
          onclick={onclose}
          aria-label={closeLabel}
        >
          <X size={18} />
        </Button>
      </div>
      <ScrollArea class="dialog-body-scroll scroll-area--dialog" maxHeight="none" type={scrollType}>
        {@render children?.()}
      </ScrollArea>
    </section>
  </div>
{/if}

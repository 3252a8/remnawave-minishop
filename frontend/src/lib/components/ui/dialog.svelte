<script>
  import { X } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";
  import { cubicOut } from "svelte/easing";
  import { onMount } from "svelte";
  import { fade, fly } from "svelte/transition";
  import Button from "./button.svelte";
  import ScrollArea from "./scroll-area.svelte";

  export let open = false;
  export let title = "";
  export let description = "";
  export let closeLabel = "Close";
  export let onclose = () => {};
  let className = "";
  export { className as class };

  function readReduceMotion() {
    return (
      typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  let reduceMotion = readReduceMotion();

  onMount(() => {
    reduceMotion = readReduceMotion();
    if (typeof window === "undefined" || !window.matchMedia) return () => {};
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = () => {
      reduceMotion = mq.matches;
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  });

  $: backdropTransition = reduceMotion ? { duration: 0 } : { duration: 200 };
  $: cardIn = reduceMotion ? { duration: 0, y: 0 } : { duration: 260, y: 16, easing: cubicOut };
  $: cardOut = reduceMotion ? { duration: 0, y: 0 } : { duration: 200, y: 10, easing: cubicOut };
</script>

{#if open}
  <div class="dialog" role="dialog" aria-modal="true" aria-label={title}>
    <button
      class="dialog-backdrop"
      type="button"
      aria-label={closeLabel}
      onclick={onclose}
      in:fade={backdropTransition}
      out:fade={backdropTransition}
    ></button>
    <section class={cn("dialog-card", className)} in:fly={cardIn} out:fly={cardOut}>
      <div class="dialog-head">
        <div class:dialog-title-with-icon={$$slots.titleIcon} class="dialog-title-block">
          {#if $$slots.titleIcon}
            <span class="dialog-title-icon" aria-hidden="true">
              <slot name="titleIcon" />
            </span>
          {/if}
          <div class="dialog-title-copy">
            {#if title}<h2>{title}</h2>{/if}
            {#if description}<p>{description}</p>{/if}
          </div>
        </div>
        <Button variant="icon" size="icon" onclick={onclose} aria-label={closeLabel}>
          <X size={18} />
        </Button>
      </div>
      <ScrollArea class="dialog-body-scroll scroll-area--dialog" maxHeight="none">
        <slot />
      </ScrollArea>
    </section>
  </div>
{/if}

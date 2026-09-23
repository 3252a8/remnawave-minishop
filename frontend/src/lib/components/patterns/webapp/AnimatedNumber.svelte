<script lang="ts">
  import NumberFlow, { type Format, type NumberFlowElement } from "@number-flow/svelte";
  import { onDestroy, untrack } from "svelte";

  let {
    value = 0,
    suffix = "",
    ariaLabel = "",
    format = {},
    className = "",
    animated = true,
    replaceAnimations = false,
    willChange = true,
    updateIntervalMs = 0,
  }: {
    value?: number;
    suffix?: string;
    ariaLabel?: string;
    format?: Format;
    className?: string;
    animated?: boolean;
    replaceAnimations?: boolean;
    willChange?: boolean;
    updateIntervalMs?: number;
  } = $props();

  let element = $state<NumberFlowElement>();
  let displayedValue = $state(untrack(() => Number(value)));
  let pendingValue = untrack(() => Number(value));
  let updateTimer: ReturnType<typeof setTimeout> | undefined;
  let lastUpdateAt = Date.now();
  let previousValue = Number.NaN;
  const resolvedFormat = $derived({ useGrouping: true, ...format });

  function commitValue(nextValue: number): void {
    if (updateTimer !== undefined) window.clearTimeout(updateTimer);
    updateTimer = undefined;
    pendingValue = nextValue;
    lastUpdateAt = Date.now();
    displayedValue = nextValue;
  }

  $effect(() => {
    const nextValue = Number(value);
    const interval = Math.max(0, Number(updateIntervalMs) || 0);
    if (Object.is(nextValue, displayedValue)) {
      if (updateTimer !== undefined) window.clearTimeout(updateTimer);
      updateTimer = undefined;
      pendingValue = nextValue;
      return;
    }
    const remaining = interval - (Date.now() - lastUpdateAt);
    if (remaining <= 0) {
      commitValue(nextValue);
      return;
    }
    pendingValue = nextValue;
    if (updateTimer === undefined) {
      updateTimer = window.setTimeout(() => commitValue(pendingValue), remaining);
    }
  });

  $effect.pre(() => {
    const nextValue = Number(displayedValue);
    if (replaceAnimations && nextValue !== previousValue && element?.animated) {
      element.animated = false;
      element.animated = true;
    }
    previousValue = nextValue;
  });

  onDestroy(() => {
    if (updateTimer !== undefined) window.clearTimeout(updateTimer);
  });
</script>

<NumberFlow
  bind:el={element}
  class={className}
  value={displayedValue}
  {suffix}
  aria-label={ariaLabel}
  format={resolvedFormat}
  {animated}
  {willChange}
/>

<script lang="ts">
  import NumberFlow, { type Format, type NumberFlowElement } from "@number-flow/svelte";

  let {
    value = 0,
    suffix = "",
    ariaLabel = "",
    format = {},
    className = "",
    replaceAnimations = false,
    willChange = true,
  }: {
    value?: number;
    suffix?: string;
    ariaLabel?: string;
    format?: Format;
    className?: string;
    replaceAnimations?: boolean;
    willChange?: boolean;
  } = $props();

  let element = $state<NumberFlowElement>();
  let previousValue = Number.NaN;
  const resolvedFormat = $derived({ useGrouping: true, ...format });

  $effect.pre(() => {
    const nextValue = Number(value);
    if (replaceAnimations && nextValue !== previousValue && element?.animated) {
      element.animated = false;
      element.animated = true;
    }
    previousValue = nextValue;
  });
</script>

<NumberFlow
  bind:el={element}
  class={className}
  {value}
  {suffix}
  aria-label={ariaLabel}
  format={resolvedFormat}
  {willChange}
/>

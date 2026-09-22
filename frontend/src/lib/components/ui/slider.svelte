<script lang="ts">
  import { onDestroy } from "svelte";
  import { Slider } from "./primitives.js";

  let {
    value = 0,
    values = [],
    ariaLabel = "",
    disabled = false,
    onValueChange = () => {},
    onInteractionChange = () => {},
  }: {
    value?: number;
    values?: number[];
    ariaLabel?: string;
    disabled?: boolean;
    onValueChange?: (value: number) => void;
    onInteractionChange?: (active: boolean) => void;
  } = $props();

  const sortedValues = $derived(
    Array.from(new Set(values.map(Number).filter(Number.isFinite))).sort((a, b) => a - b)
  );
  const maximumIndex = $derived(Math.max(0, sortedValues.length - 1));
  const selectedIndex = $derived.by(() => {
    const exactIndex = sortedValues.findIndex(
      (candidate) => Math.abs(candidate - Number(value)) < 1e-9
    );
    return exactIndex >= 0 ? exactIndex : 0;
  });
  const effectivelyDisabled = $derived(disabled || sortedValues.length <= 1);
  let sliderIndex = $state(0);
  let interactionActive = $state(false);
  let lastEmittedValue = 0;
  let pendingValue: number | undefined;
  let valueChangeTimer: ReturnType<typeof setTimeout> | undefined;
  let lastEmitTime = 0;
  const valueChangeIntervalMs = 140;

  $effect.pre(() => {
    values;
    if (interactionActive) return;
    sliderIndex = selectedIndex;
    lastEmittedValue = Number(value);
  });

  function setInteractionActive(active: boolean): void {
    if (interactionActive === active) return;
    interactionActive = active;
    onInteractionChange(active);
  }

  function emitPendingValue(): void {
    valueChangeTimer = undefined;
    const nextValue = pendingValue;
    pendingValue = undefined;
    if (nextValue == null || Math.abs(nextValue - lastEmittedValue) < 1e-9) return;
    lastEmittedValue = nextValue;
    lastEmitTime = performance.now();
    onValueChange(nextValue);
  }

  function flushPendingValue(): void {
    if (valueChangeTimer !== undefined) window.clearTimeout(valueChangeTimer);
    emitPendingValue();
  }

  function handleIndexChange(nextIndex: number): void {
    const index = Math.max(0, Math.min(maximumIndex, Math.round(nextIndex)));
    const nextValue = sortedValues[index];
    const latestValue = pendingValue ?? lastEmittedValue;
    if (nextValue == null || Math.abs(nextValue - latestValue) < 1e-9) return;
    pendingValue = nextValue;
    if (valueChangeTimer === undefined) {
      const elapsed = performance.now() - lastEmitTime;
      valueChangeTimer = window.setTimeout(
        emitPendingValue,
        Math.max(0, valueChangeIntervalMs - elapsed)
      );
    }
  }

  function handlePointerDown(): void {
    if (!effectivelyDisabled) setInteractionActive(true);
  }

  function handlePointerEnd(): void {
    flushPendingValue();
    setInteractionActive(false);
  }

  onDestroy(() => {
    if (valueChangeTimer !== undefined) window.clearTimeout(valueChangeTimer);
    pendingValue = undefined;
    setInteractionActive(false);
  });
</script>

<svelte:window onpointerup={handlePointerEnd} onpointercancel={handlePointerEnd} />

<Slider.Root
  class={`checkout-slider${interactionActive ? " is-interacting" : ""}`}
  type="single"
  bind:value={sliderIndex}
  min={0}
  max={maximumIndex}
  step={1}
  aria-label={ariaLabel}
  disabled={effectivelyDisabled}
  onValueChange={handleIndexChange}
  onpointerdown={handlePointerDown}
>
  {#snippet children({ thumbItems })}
    <span class="checkout-slider-track">
      <Slider.Range class="checkout-slider-range" />
    </span>
    <span class="checkout-slider-ticks" aria-hidden="true">
      {#each sortedValues as tickValue, index (tickValue)}
        <span
          class={`checkout-slider-tick${index <= sliderIndex ? " active" : ""}`}
          style={`left: ${maximumIndex > 0 ? (index / maximumIndex) * 100 : 0}%`}
        >
          <span></span>
        </span>
      {/each}
    </span>
    {#each thumbItems as thumb (thumb.index)}
      <Slider.Thumb class="checkout-slider-thumb" index={thumb.index} aria-label={ariaLabel} />
    {/each}
  {/snippet}
</Slider.Root>

<style>
  :global(.checkout-slider) {
    --checkout-slider-thumb-size: 0.82rem;

    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
    height: 1rem;
    touch-action: none;
    user-select: none;
    cursor: pointer;
  }

  .checkout-slider-track {
    position: relative;
    display: block;
    width: 100%;
    height: 0.34rem;
    overflow: hidden;
    border-radius: 999px;
    background: color-mix(in srgb, var(--border, #334155) 72%, var(--panel, #0f172a));
  }

  :global(.checkout-slider-range) {
    position: absolute;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 76%, white));
    box-shadow: 0 0 0.8rem color-mix(in srgb, var(--accent) 34%, transparent);
    transition: width 120ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  :global(.checkout-slider.is-interacting .checkout-slider-range) {
    transition: none;
  }

  .checkout-slider-ticks {
    position: absolute;
    inset: 0 calc(var(--checkout-slider-thumb-size) / 2);
    z-index: 2;
    pointer-events: none;
  }

  .checkout-slider-tick {
    position: absolute;
    top: 50%;
    display: grid;
    width: 0.58rem;
    height: 0.58rem;
    transform: translate(-50%, -50%);
    place-items: center;
    pointer-events: none;
  }

  .checkout-slider-tick > span {
    width: 0.19rem;
    height: 0.19rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--muted, #94a3b8) 82%, white 18%);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--panel, #0f172a) 42%, transparent);
    transition:
      background 140ms ease,
      box-shadow 140ms ease,
      scale 140ms ease;
  }

  .checkout-slider-tick.active > span {
    scale: 1.08;
    background: color-mix(in srgb, var(--panel, #07120d) 86%, black 14%);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 62%, transparent);
  }

  :global(.checkout-slider-thumb) {
    position: absolute;
    top: 50%;
    z-index: 3;
    width: var(--checkout-slider-thumb-size);
    height: var(--checkout-slider-thumb-size);
    transform: translateY(-50%);
    border: 0.15rem solid var(--accent);
    border-radius: 999px;
    outline: none;
    background: var(--panel, #0f172a);
    box-shadow:
      0 0 0 0.11rem color-mix(in srgb, var(--panel, #0f172a) 84%, transparent),
      0 0.1rem 0.55rem color-mix(in srgb, var(--accent) 38%, transparent);
    transition:
      scale 120ms ease,
      box-shadow 120ms ease;
  }

  :global(.checkout-slider-thumb:hover),
  :global(.checkout-slider-thumb:focus-visible),
  :global(.checkout-slider-thumb[data-active]) {
    scale: 1.09;
    box-shadow:
      0 0 0 0.14rem color-mix(in srgb, var(--panel, #0f172a) 84%, transparent),
      0 0.12rem 0.7rem color-mix(in srgb, var(--accent) 50%, transparent);
  }

  :global(.checkout-slider[data-disabled]) {
    cursor: default;
    opacity: 0.58;
  }
</style>

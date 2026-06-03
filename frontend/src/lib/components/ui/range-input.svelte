<script>
  import { cn } from "$lib/utils.js";
  import { Slider } from "./primitives.js";

  export let value = 0;
  export let min = undefined;
  export let max = undefined;
  export let step = undefined;
  export let disabled = false;
  export let ariaLabel = "";
  export let onValueChange = () => {};
  export let onValueCommit = () => {};
  let className = "";
  export { className as class };

  $: sliderMin = min === undefined ? undefined : Number(min);
  $: sliderMax = max === undefined ? undefined : Number(max);
  $: sliderStep = step === undefined ? undefined : Number(step);
  $: sliderValue = normalizeSliderValue(value, sliderMin ?? 0);

  function normalizeSliderValue(next, fallback = 0) {
    const raw = Array.isArray(next) ? next[0] : next;
    const numeric = Number(raw);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function handleValueChange(next) {
    const normalized = normalizeSliderValue(next, sliderMin ?? 0);
    value = normalized;
    onValueChange(normalized);
  }

  function handleValueCommit(next) {
    onValueCommit(normalizeSliderValue(next, sliderMin ?? 0));
  }
</script>

<Slider.Root
  class={cn("ui-range-input", className)}
  type="single"
  value={sliderValue}
  min={sliderMin}
  max={sliderMax}
  step={sliderStep}
  {disabled}
  onValueChange={handleValueChange}
  onValueCommit={handleValueCommit}
  {...$$restProps}
>
  <Slider.Range class="ui-range-input__range" />
  <Slider.Thumb class="ui-range-input__thumb" aria-label={ariaLabel} />
</Slider.Root>

<style>
  :global(.ui-range-input) {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
    height: 18px;
    touch-action: none;
    user-select: none;
  }

  :global(.ui-range-input::before) {
    content: "";
    position: absolute;
    right: 0;
    left: 0;
    height: 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-border-strong, var(--border)) 70%, transparent);
  }

  :global(.ui-range-input__range) {
    position: absolute;
    height: 5px;
    border-radius: 999px;
    background: var(--accent);
  }

  :global(.ui-range-input__thumb) {
    display: block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--accent);
    border-radius: 999px;
    background: var(--admin-surface, var(--panel));
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.24);
    outline: none;
    transition:
      box-shadow 0.14s ease,
      transform 0.14s ease;
  }

  :global(.ui-range-input__thumb:hover) {
    transform: scale(1.05);
  }

  :global(.ui-range-input__thumb:focus-visible) {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 24%, transparent);
  }

  :global(.ui-range-input[data-disabled]) {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>

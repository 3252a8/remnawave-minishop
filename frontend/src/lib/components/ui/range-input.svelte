<script lang="ts">
  import type { HTMLInputAttributes } from "svelte/elements";
  import { cn } from "$lib/utils.js";

  type NumericInput = number | string | undefined;
  type RangeInputProps = Omit<
    HTMLInputAttributes,
    | "id"
    | "type"
    | "value"
    | "name"
    | "min"
    | "max"
    | "step"
    | "disabled"
    | "oninput"
    | "onchange"
    | "onValueChange"
    | "onValueCommit"
    | "class"
  > & {
    id?: string;
    value?: number | string;
    name?: string;
    min?: NumericInput;
    max?: NumericInput;
    step?: NumericInput;
    disabled?: boolean;
    ariaLabel?: string;
    onValueChange?: unknown;
    onValueCommit?: unknown;
    class?: string;
  };

  let {
    id = "",
    value = $bindable(0),
    name = undefined,
    min = undefined,
    max = undefined,
    step = undefined,
    disabled = false,
    ariaLabel = "",
    onValueChange = undefined,
    onValueCommit = undefined,
    class: className = "",
    ...rest
  }: RangeInputProps = $props();

  const fallbackId = `ui-range-input-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const inputId = $derived(id || fallbackId);
  const sliderMin = $derived(min === undefined ? undefined : Number(min));
  const sliderMax = $derived(max === undefined ? undefined : Number(max));
  const sliderStep = $derived(step === undefined ? undefined : Number(step));
  const sliderValue = $derived(normalizeSliderValue(value, sliderMin ?? 0));
  const sliderProgress = $derived(progressPercent(sliderValue, sliderMin, sliderMax));

  function normalizeSliderValue(next: number | string | undefined, fallback = 0): number {
    const raw = next;
    const numeric = Number(raw);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function progressPercent(
    next: number,
    minValue: number | undefined,
    maxValue: number | undefined
  ): number {
    const low = Number.isFinite(minValue) ? Number(minValue) : 0;
    const high = Number.isFinite(maxValue) ? Number(maxValue) : 100;
    if (high <= low) return 0;
    const percent = ((next - low) / (high - low)) * 100;
    return Math.min(100, Math.max(0, percent));
  }

  function readEventValue(event: Event): number {
    const target = event.currentTarget as HTMLInputElement | null;
    return normalizeSliderValue(target?.value, sliderMin ?? 0);
  }

  function handleInput(event: Event): void {
    const normalized = readEventValue(event);
    value = normalized;
    callValueCallback(onValueChange, normalized);
  }

  function handleChange(event: Event): void {
    const normalized = readEventValue(event);
    value = normalized;
    callValueCallback(onValueCommit, normalized);
  }

  function callValueCallback(callback: unknown, next: number): void {
    if (typeof callback === "function") {
      (callback as (value: number) => void)(next);
    }
  }
</script>

<input
  id={inputId}
  class={cn("ui-range-input", className)}
  type="range"
  {name}
  value={sliderValue}
  min={sliderMin}
  max={sliderMax}
  step={sliderStep}
  {disabled}
  aria-label={ariaLabel}
  style={`--range-progress:${sliderProgress}%`}
  oninput={handleInput}
  onchange={handleChange}
  {...rest}
/>

<style>
  :global(.ui-range-input) {
    appearance: none;
    width: 100%;
    height: 18px;
    margin: 0;
    background: transparent;
    cursor: pointer;
  }

  :global(.ui-range-input::-webkit-slider-runnable-track) {
    height: 5px;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      var(--accent) 0 var(--range-progress, 0%),
      color-mix(in srgb, var(--admin-border-strong, var(--border)) 70%, transparent)
        var(--range-progress, 0%) 100%
    );
  }

  :global(.ui-range-input::-moz-range-track) {
    height: 5px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-border-strong, var(--border)) 70%, transparent);
  }

  :global(.ui-range-input::-moz-range-progress) {
    height: 5px;
    border-radius: 999px;
    background: var(--accent);
  }

  :global(.ui-range-input::-webkit-slider-thumb) {
    appearance: none;
    width: 16px;
    height: 16px;
    margin-top: -5.5px;
    border: 2px solid var(--accent);
    border-radius: 999px;
    background: var(--admin-surface, var(--panel));
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.24);
    outline: none;
    transition:
      box-shadow 0.14s ease,
      transform 0.14s ease;
  }

  :global(.ui-range-input::-moz-range-thumb) {
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

  :global(.ui-range-input:hover::-webkit-slider-thumb),
  :global(.ui-range-input:hover::-moz-range-thumb) {
    transform: scale(1.05);
  }

  :global(.ui-range-input:focus-visible::-webkit-slider-thumb),
  :global(.ui-range-input:focus-visible::-moz-range-thumb) {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 24%, transparent);
  }

  :global(.ui-range-input:disabled) {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>

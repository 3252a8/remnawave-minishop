<script lang="ts">
  import { cn } from "$lib/utils.js";
  import ColorPicker from "svelte-awesome-color-picker";
  import { MediaQuery } from "svelte/reactivity";
  import { Popover } from "./primitives.js";
  import { Check, X } from "./icons.js";
  import ColorPickerPanel from "./color-picker-panel.svelte";
  import {
    colorInputOpacity,
    colorInputValueChanged,
    colorInputWithOpacity,
    normalizeColorInput,
  } from "./colorInputValue";

  type ColorInputEvent = Event & { currentTarget: EventTarget & HTMLInputElement };
  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    value = $bindable("#000000"),
    name = undefined,
    disabled = false,
    allowAlpha = false,
    ariaLabel = "",
    class: className = "",
    translate,
    oninput,
  }: {
    value?: string;
    name?: string;
    disabled?: boolean;
    /** Enable only when the receiving setting accepts CSS colors with alpha. */
    allowAlpha?: boolean;
    ariaLabel?: string;
    class?: string;
    translate?: TranslateFn;
    oninput?: (event: ColorInputEvent) => void;
  } = $props();

  const swatches = [
    "#ffffff",
    "#171c26",
    "#00fe7a",
    "#38bdf8",
    "#818cf8",
    "#e879f9",
    "#fb7185",
    "#fbbf24",
  ];
  const uid = $props.id();
  const compact = new MediaQuery("(max-width: 600px)");
  let open = $state(false);
  let inputElement: HTMLInputElement;
  let pickerHex = $state<string | null>("#000000");
  let previous = $state("#000000");
  let hexText = $state("");
  let invalidHex = $state(false);
  const color = $derived(normalizeColorInput(value, allowAlpha) ?? "#000000");
  const opacity = $derived(colorInputOpacity(color));
  const text = (key: string, fallback: string, params: Record<string, unknown> = {}) =>
    translate?.(`color_picker_${key}`, params, fallback) ?? fallback;

  $effect(() => {
    if (colorInputValueChanged(pickerHex ?? "", color)) pickerHex = color;
    hexText = color.toUpperCase();
    invalidHex = false;
  });

  function emitInput(next: string): void {
    const normalized = normalizeColorInput(next, allowAlpha);
    if (disabled || !normalized || !colorInputValueChanged(color, normalized)) return;
    value = normalized;
    inputElement.value = normalized;
    inputElement.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function changeOpen(next: boolean): void {
    if (next) {
      previous = color;
      hexText = color.toUpperCase();
      invalidHex = false;
    }
    open = next;
  }

  function commitHex(): void {
    const next = normalizeColorInput(hexText, allowAlpha);
    invalidHex = !next;
    if (next) {
      emitInput(next);
      hexText = next.toUpperCase();
    }
  }
</script>

{#snippet panel()}
  <div class="ui-color-picker-head">
    <strong>{ariaLabel || text("title", "Color")}</strong>
    <Popover.Close class="ui-color-close" aria-label={text("close", "Close color picker")}>
      <X size={16} />
    </Popover.Close>
  </div>
  <ColorPicker
    bind:hex={pickerHex}
    components={{ wrapper: ColorPickerPanel }}
    isDialog={false}
    isTextInput={false}
    isAlpha={allowAlpha}
    sliderDirection="horizontal"
    texts={{
      label: {
        h: text("hue", "Hue"),
        s: text("saturation", "Saturation"),
        v: text("brightness", "Brightness"),
        a: text("opacity", "Opacity"),
      },
    }}
    --picker-height="164px"
    --picker-width="min(254px, calc(100vw - 58px))"
    onInput={(event) => event.hex && emitInput(event.hex)}
  />
  <div class="ui-color-values">
    <label class="ui-color-hex" for={`${uid}-hex`}>
      <span>{text("hex", "HEX")}</span>
      <input
        id={`${uid}-hex`}
        type="text"
        bind:value={hexText}
        spellcheck={false}
        autocomplete="off"
        maxlength={allowAlpha ? 9 : 7}
        aria-invalid={invalidHex}
        aria-describedby={invalidHex ? `${uid}-error` : undefined}
        onblur={commitHex}
        onkeydown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commitHex();
          }
        }}
      />
    </label>
    {#if allowAlpha}
      <label class="ui-color-opacity" for={`${uid}-opacity`}>
        <span>{text("opacity", "Opacity")}</span>
        <div>
          <input
            id={`${uid}-opacity`}
            type="number"
            min="0"
            max="100"
            step="1"
            value={opacity}
            onblur={(event) => (event.currentTarget.value = String(opacity))}
            oninput={(event) => {
              const next = event.currentTarget.valueAsNumber;
              if (Number.isFinite(next)) emitInput(colorInputWithOpacity(color, next));
            }}
          />
          <span aria-hidden="true">%</span>
        </div>
      </label>
    {/if}
  </div>
  {#if invalidHex}
    <p id={`${uid}-error`} class="ui-color-error">
      {text("invalid_hex", "Enter a valid HEX color")}
    </p>
  {/if}
  <div class="ui-color-presets" role="group" aria-label={text("presets", "Color presets")}>
    {#each swatches as swatch (swatch)}
      <button
        type="button"
        class="ui-color-preset"
        aria-label={text("preset", "Choose {color}", { color: swatch.toUpperCase() })}
        aria-pressed={color.slice(0, 7) === swatch}
        onclick={() => emitInput(allowAlpha ? `${swatch}${color.slice(7)}` : swatch)}
      >
        <span class="ui-color-swatch" style:--swatch-color={swatch}></span>
        {#if color.slice(0, 7) === swatch}<Check size={13} />{/if}
      </button>
    {/each}
  </div>
  <div class="ui-color-picker-foot">
    <button type="button" class="ui-color-previous" onclick={() => emitInput(previous)}>
      <span class="ui-color-swatch" style:--swatch-color={previous}></span>
      {text("previous", "Previous color")}
    </button>
    <span class="ui-color-current ui-color-swatch" style:--swatch-color={color} aria-hidden="true"
    ></span>
  </div>
{/snippet}

<div class={cn("ui-color-input", className)}>
  <input bind:this={inputElement} type="hidden" {name} {value} {disabled} {oninput} />
  <Popover.Root {open} onOpenChange={changeOpen}>
    <Popover.Trigger
      type="button"
      class="ui-color-trigger"
      {disabled}
      aria-label={ariaLabel || text("title", "Color")}
      title={`${ariaLabel || text("title", "Color")}: ${color.toUpperCase()}`}
    >
      <span class="ui-color-swatch" style:--swatch-color={value ? color : "transparent"}></span>
    </Popover.Trigger>
    <Popover.Portal>
      {#if compact.current}
        <Popover.ContentStatic
          class="ui-color-picker ui-color-picker-mobile"
          role="dialog"
          trapFocus={true}
          aria-label={ariaLabel || text("title", "Color")}
        >
          {@render panel()}
        </Popover.ContentStatic>
      {:else}
        <Popover.Content
          class="ui-color-picker"
          role="dialog"
          side="right"
          align="start"
          sideOffset={8}
          collisionPadding={12}
          sticky="always"
          trapFocus={true}
          aria-label={ariaLabel || text("title", "Color")}
        >
          {@render panel()}
        </Popover.Content>
      {/if}
    </Popover.Portal>
  </Popover.Root>
</div>

<style>
  .ui-color-input {
    width: 38px;
    height: 38px;
    flex: 0 0 38px;
  }
  .ui-color-input :global(.ui-color-trigger) {
    display: block;
    width: 100%;
    height: 100%;
    padding: 5px;
    cursor: pointer;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: var(--radius-control, 9px);
    background: var(--admin-surface-2, var(--panel-2));
    transition:
      border-color 140ms,
      box-shadow 140ms;
  }
  .ui-color-input :global(.ui-color-trigger:hover:not(:disabled)),
  .ui-color-input :global(.ui-color-trigger[data-state="open"]) {
    border-color: var(--accent);
  }
  .ui-color-input :global(.ui-color-trigger:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .ui-color-input :global(.ui-color-trigger:disabled) {
    opacity: 0.42;
    cursor: not-allowed;
  }
  :global(.ui-color-swatch) {
    display: block;
    width: 100%;
    height: 100%;
    border-radius: 5px;
    background:
      linear-gradient(var(--swatch-color), var(--swatch-color)),
      repeating-conic-gradient(#8c929e 0% 25%, #e0e3e9 0% 50%) 0 0 / 8px 8px;
    box-shadow: inset 0 0 0 1px #80808028;
  }
  :global(.ui-color-picker) {
    box-sizing: border-box;
    z-index: 1200;
    width: min(288px, calc(100vw - 24px));
    max-height: calc(100dvh - 24px);
    overflow-y: auto;
    padding: 16px;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 16px;
    background: var(--admin-surface, var(--panel));
    color: var(--admin-text, var(--text));
    box-shadow:
      0 18px 54px #00000040,
      0 2px 8px #00000020;
    font-family: var(--font-sans, sans-serif);
    font-size: 12px;
  }
  :global(.ui-color-picker-mobile) {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }
  .ui-color-picker-head,
  .ui-color-picker-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .ui-color-picker-head {
    margin-bottom: 12px;
  }
  .ui-color-picker-head strong {
    font-size: 13px;
    overflow-wrap: anywhere;
  }
  :global(.ui-color-close) {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    flex-shrink: 0;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  :global(.ui-color-close:hover) {
    background: var(--admin-surface-2, var(--panel-2));
  }
  :global(.ui-color-picker .color-picker) {
    display: block;
    width: 100%;
  }
  :global(.ui-color-picker .picker) {
    border-radius: 10px;
  }
  :global(.ui-color-picker .color-picker.horizontal .h),
  :global(.ui-color-picker .color-picker.horizontal .a) {
    --track-width: min(242px, calc(100vw - 70px));
    --track-height: 12px;
    --track-border-radius: 8px;
    --thumb-size: 18px;
    --thumb-border: 2px solid white;
    --thumb-border-radius: 50%;
    --thumb-box-shadow: 0 1px 5px #0008;
    margin: 8px 0;
  }
  .ui-color-values {
    display: flex;
    gap: 10px;
    margin-top: 8px;
  }
  .ui-color-values label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .ui-color-values label > span {
    font-size: 10px;
    font-weight: 600;
    color: var(--admin-muted, var(--muted));
  }
  .ui-color-hex {
    flex: 1;
  }
  .ui-color-opacity {
    width: 92px;
  }
  .ui-color-values input {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    height: 36px;
    padding: 0 9px;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 8px;
    background: var(--admin-surface-2, var(--panel-2));
    color: inherit;
    font: 12px var(--font-mono, monospace);
  }
  .ui-color-values input:focus {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .ui-color-values input[aria-invalid="true"] {
    border-color: var(--danger);
  }
  .ui-color-opacity > div {
    position: relative;
  }
  .ui-color-opacity input {
    padding-right: 22px;
    appearance: textfield;
  }
  .ui-color-opacity input::-webkit-inner-spin-button {
    appearance: none;
  }
  .ui-color-opacity div > span {
    position: absolute;
    right: 9px;
    top: 10px;
    color: var(--admin-muted, var(--muted));
    pointer-events: none;
  }
  .ui-color-error {
    margin: 8px 0 0;
    color: var(--danger);
  }
  .ui-color-presets {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 7px;
    margin-top: 16px;
  }
  .ui-color-preset {
    position: relative;
    aspect-ratio: 1;
    padding: 0;
    border: 0;
    border-radius: 5px;
    cursor: pointer;
  }
  .ui-color-preset[aria-pressed="true"] {
    outline: 2px solid var(--admin-text, var(--text));
    outline-offset: 2px;
  }
  .ui-color-preset :global(svg) {
    position: absolute;
    inset: 0;
    margin: auto;
    color: white;
    filter: drop-shadow(0 1px 2px #000);
  }
  .ui-color-picker-foot {
    border-top: 1px solid var(--admin-border, var(--border));
    padding-top: 12px;
    margin-top: 16px;
  }
  .ui-color-previous {
    display: flex;
    align-items: center;
    gap: 8px;
    border: 0;
    padding: 0;
    background: none;
    color: var(--admin-muted, var(--muted));
    font: inherit;
    cursor: pointer;
  }
  .ui-color-previous .ui-color-swatch {
    width: 22px;
    height: 22px;
  }
  .ui-color-current {
    width: 42px;
    height: 26px;
  }
  .ui-color-previous:focus-visible,
  .ui-color-preset:focus-visible,
  :global(.ui-color-close:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
</style>

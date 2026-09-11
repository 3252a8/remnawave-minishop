<script lang="ts">
  import { cn } from "$lib/utils.js";
  import ColorPicker from "svelte-awesome-color-picker";
  import ColorPickerTrigger from "./color-picker-trigger.svelte";
  import { colorInputValueChanged } from "./colorInputValue";

  type ColorInputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };

  type ColorInputProps = {
    value?: string;
    name?: string;
    disabled?: boolean;
    ariaLabel?: string;
    class?: string;
    oninput?: (event: ColorInputEventWithTarget) => void;
  };

  let {
    value = $bindable("#000000"),
    name = undefined,
    disabled = false,
    ariaLabel = "",
    class: className = "",
    oninput,
  }: ColorInputProps = $props();

  function forwardInput(event: ColorInputEventWithTarget) {
    oninput?.(event);
  }

  let pickerHex = $state(value || "#000000");

  function emitInput(nextHex: string) {
    if (!colorInputValueChanged(value, nextHex)) return;
    value = nextHex;
    const event = new Event("input", { bubbles: true });
    Object.defineProperty(event, "currentTarget", { value: { value: nextHex } });
    forwardInput(event as ColorInputEventWithTarget);
  }

  $effect(() => {
    const nextValue = value || "#000000";
    if (pickerHex !== nextValue) pickerHex = nextValue;
  });
</script>

<div class={cn("ui-color-input", className)}>
  {#if disabled}
    <span
      class="ui-color-input-disabled"
      style:background-color={value ? pickerHex : "transparent"}
      aria-label={ariaLabel}
      aria-disabled="true"
    ></span>
  {:else}
    <ColorPicker
      bind:hex={pickerHex}
      components={{ input: ColorPickerTrigger }}
      label={ariaLabel}
      {name}
      isAlpha={false}
      position="responsive"
      --picker-height="150px"
      --picker-width="190px"
      --input-size="30px"
      --cp-bg-color="var(--admin-surface)"
      --cp-border-color="var(--admin-border)"
      --cp-text-color="var(--admin-text)"
      --cp-input-color="var(--admin-surface-2)"
      --cp-button-hover-color="var(--admin-surface-3)"
      onInput={(event) => emitInput(event.hex || "#000000")}
    />
  {/if}
</div>

<style>
  .ui-color-input-disabled {
    display: block;
    width: 100%;
    height: 100%;
    border-radius: inherit;
    opacity: 0.42;
  }
</style>

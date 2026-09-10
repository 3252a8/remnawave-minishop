<script lang="ts">
  import { cn } from "$lib/utils.js";
  import ColorPicker from "svelte-awesome-color-picker";
  import type { HTMLInputAttributes } from "svelte/elements";
  import ColorPickerTrigger from "./color-picker-trigger.svelte";
  import { colorInputValueChanged } from "./colorInputValue";

  type ColorInputProps = Omit<
    HTMLInputAttributes,
    "id" | "value" | "type" | "name" | "disabled" | "aria-label" | "class" | "oninput" | "onchange"
  > & {
    id?: string;
    value?: string;
    name?: string;
    disabled?: boolean;
    ariaLabel?: string;
    class?: string;
    oninput?: HTMLInputAttributes["oninput"];
    onchange?: HTMLInputAttributes["onchange"];
  };

  type ColorInputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };

  let {
    id = "",
    value = $bindable("#000000"),
    name = undefined,
    disabled = false,
    ariaLabel = "",
    class: className = "",
    oninput,
    onchange,
    ...rest
  }: ColorInputProps = $props();

  const fallbackId = `ui-color-input-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const inputId = $derived(id || fallbackId);

  function forwardInput(event: ColorInputEventWithTarget) {
    oninput?.(event);
  }

  function forwardChange(event: ColorInputEventWithTarget) {
    onchange?.(event);
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
      name={name}
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
      {...rest}
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

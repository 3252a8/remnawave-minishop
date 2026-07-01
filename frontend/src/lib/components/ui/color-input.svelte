<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

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
</script>

<input
  id={inputId}
  bind:value
  class={cn("ui-color-input", className)}
  type="color"
  {name}
  {disabled}
  aria-label={ariaLabel}
  oninput={forwardInput}
  onchange={forwardChange}
  {...rest}
/>

<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type ColorInputProps = Omit<
    HTMLInputAttributes,
    "value" | "type" | "disabled" | "aria-label" | "class" | "oninput" | "onchange"
  > & {
    value?: string;
    disabled?: boolean;
    ariaLabel?: string;
    class?: string;
    oninput?: HTMLInputAttributes["oninput"];
    onchange?: HTMLInputAttributes["onchange"];
  };

  type ColorInputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };

  let {
    value = $bindable("#000000"),
    disabled = false,
    ariaLabel = "",
    class: className = "",
    oninput,
    onchange,
    ...rest
  }: ColorInputProps = $props();

  function forwardInput(event: ColorInputEventWithTarget) {
    oninput?.(event);
  }

  function forwardChange(event: ColorInputEventWithTarget) {
    onchange?.(event);
  }
</script>

<input
  bind:value
  class={cn("ui-color-input", className)}
  type="color"
  {disabled}
  aria-label={ariaLabel}
  oninput={forwardInput}
  onchange={forwardChange}
  {...rest}
/>

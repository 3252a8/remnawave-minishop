<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type InputProps = Omit<
    HTMLInputAttributes,
    | "value"
    | "type"
    | "placeholder"
    | "inputmode"
    | "maxlength"
    | "autocomplete"
    | "disabled"
    | "class"
    | "onkeydown"
    | "oninput"
    | "onfocus"
    | "onblur"
  > & {
    value?: string | number;
    type?: HTMLInputAttributes["type"];
    placeholder?: string;
    inputmode?: string | null | undefined;
    maxlength?: HTMLInputAttributes["maxlength"];
    autocomplete?: HTMLInputAttributes["autocomplete"];
    disabled?: boolean;
    class?: string;
    onkeydown?: HTMLInputAttributes["onkeydown"];
    oninput?: HTMLInputAttributes["oninput"];
    onfocus?: HTMLInputAttributes["onfocus"];
    onblur?: HTMLInputAttributes["onblur"];
  };

  type InputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };
  type KeyboardEventWithTarget = KeyboardEvent & { currentTarget: EventTarget & HTMLInputElement };
  type FocusEventWithTarget = FocusEvent & { currentTarget: EventTarget & HTMLInputElement };

  let {
    value = $bindable(""),
    type = "text",
    placeholder = "",
    inputmode = undefined,
    maxlength = undefined,
    autocomplete = undefined,
    disabled = false,
    class: className = "",
    onkeydown,
    oninput,
    onfocus,
    onblur,
    ...rest
  }: InputProps = $props();

  const inputmodeAttr = $derived(inputmode as HTMLInputAttributes["inputmode"]);

  function forwardKeydown(event: KeyboardEventWithTarget) {
    onkeydown?.(event);
  }

  function forwardInput(event: InputEventWithTarget) {
    oninput?.(event);
  }

  function forwardFocus(event: FocusEventWithTarget) {
    onfocus?.(event);
  }

  function forwardBlur(event: FocusEventWithTarget) {
    onblur?.(event);
  }
</script>

<input
  bind:value
  class={cn("input", className)}
  onkeydown={forwardKeydown}
  oninput={forwardInput}
  onfocus={forwardFocus}
  onblur={forwardBlur}
  {type}
  {placeholder}
  inputmode={inputmodeAttr}
  {maxlength}
  {autocomplete}
  {disabled}
  {...rest}
/>

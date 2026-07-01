<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type InputProps = Omit<
    HTMLInputAttributes,
    | "id"
    | "value"
    | "type"
    | "name"
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
    id?: string;
    value?: string | number;
    type?: HTMLInputAttributes["type"];
    name?: string;
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
    id = "",
    value = $bindable(""),
    type = "text",
    name = undefined,
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

  const fallbackId = `ui-input-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const inputId = $derived(id || fallbackId);
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
  id={inputId}
  bind:value
  class={cn("input", className)}
  onkeydown={forwardKeydown}
  oninput={forwardInput}
  onfocus={forwardFocus}
  onblur={forwardBlur}
  {type}
  {name}
  {placeholder}
  inputmode={inputmodeAttr}
  {maxlength}
  {autocomplete}
  {disabled}
  {...rest}
/>

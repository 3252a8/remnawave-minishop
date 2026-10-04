<script lang="ts">
  import { cn } from "$lib/utils.js";
  import { controlSizeClass, type ControlSize } from "./controlSize";
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
    type?: "text" | "search" | "email" | "url" | "tel" | "password" | "number" | "hidden";
    name?: string;
    placeholder?: string;
    inputmode?: string | null | undefined;
    maxlength?: HTMLInputAttributes["maxlength"];
    autocomplete?: HTMLInputAttributes["autocomplete"];
    disabled?: boolean;
    class?: string;
    controlSize?: ControlSize;
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
    controlSize,
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
  class={cn("input", controlSizeClass(controlSize), className)}
  data-control-size={controlSize}
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

<style>
  /* The admin context already specifies 36px height; the public input's 46px
     minimum must not defeat that density. Explicit controlSize wins separately. */
  :global(.admin-screen-wrap) .input:not([data-control-size]),
  :global(.admin-dialog) .input:not([data-control-size]) {
    min-height: 36px;
  }

  @media (max-width: 560px) {
    .input[data-control-size] {
      font-size: 16px;
    }
  }
</style>

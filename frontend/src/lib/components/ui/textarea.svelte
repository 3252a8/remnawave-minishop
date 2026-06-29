<script lang="ts">
  import type { HTMLTextareaAttributes } from "svelte/elements";

  type TextareaProps = Omit<
    HTMLTextareaAttributes,
    | "id"
    | "value"
    | "name"
    | "rows"
    | "disabled"
    | "placeholder"
    | "maxlength"
    | "aria-label"
    | "class"
    | "oninput"
    | "onkeydown"
  > & {
    id?: string;
    value?: string;
    name?: string;
    rows?: number;
    disabled?: boolean;
    placeholder?: string;
    maxlength?: HTMLTextareaAttributes["maxlength"];
    ariaLabel?: string;
    class?: string;
    oninput?: HTMLTextareaAttributes["oninput"];
    onkeydown?: HTMLTextareaAttributes["onkeydown"];
  };

  type TextareaEventWithTarget = Event & { currentTarget: EventTarget & HTMLTextAreaElement };
  type TextareaKeyboardEventWithTarget = KeyboardEvent & {
    currentTarget: EventTarget & HTMLTextAreaElement;
  };

  let {
    id = "",
    value = $bindable(""),
    name = undefined,
    rows = 3,
    disabled = false,
    placeholder = "",
    maxlength = undefined,
    ariaLabel = "",
    class: className = "",
    oninput,
    onkeydown,
    ...rest
  }: TextareaProps = $props();

  const fallbackId = `ui-textarea-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const textareaId = $derived(id || fallbackId);

  function forwardInput(event: TextareaEventWithTarget) {
    oninput?.(event);
  }

  function forwardKeydown(event: TextareaKeyboardEventWithTarget) {
    onkeydown?.(event);
  }
</script>

<textarea
  id={textareaId}
  class={`textarea ${className}`.trim()}
  bind:value
  {name}
  {rows}
  {disabled}
  {placeholder}
  {maxlength}
  aria-label={ariaLabel || placeholder}
  oninput={forwardInput}
  onkeydown={forwardKeydown}
  {...rest}></textarea>

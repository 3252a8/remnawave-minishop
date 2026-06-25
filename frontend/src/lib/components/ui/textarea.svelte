<script lang="ts">
  import type { HTMLTextareaAttributes } from "svelte/elements";

  type TextareaProps = Omit<
    HTMLTextareaAttributes,
    | "value"
    | "rows"
    | "disabled"
    | "placeholder"
    | "maxlength"
    | "aria-label"
    | "class"
    | "oninput"
    | "onkeydown"
  > & {
    value?: string;
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
    value = $bindable(""),
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

  function forwardInput(event: TextareaEventWithTarget) {
    oninput?.(event);
  }

  function forwardKeydown(event: TextareaKeyboardEventWithTarget) {
    onkeydown?.(event);
  }
</script>

<textarea
  class={`textarea ${className}`.trim()}
  bind:value
  {rows}
  {disabled}
  {placeholder}
  {maxlength}
  aria-label={ariaLabel || placeholder}
  oninput={forwardInput}
  onkeydown={forwardKeydown}
  {...rest}
></textarea>

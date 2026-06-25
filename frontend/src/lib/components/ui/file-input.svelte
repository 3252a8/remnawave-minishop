<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type FileInputProps = Omit<
    HTMLInputAttributes,
    "type" | "accept" | "disabled" | "class" | "onchange"
  > & {
    element?: HTMLInputElement | null;
    accept?: string | undefined;
    disabled?: boolean;
    class?: string;
    onchange?: HTMLInputAttributes["onchange"];
  };

  type FileInputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };

  let {
    element = $bindable(null),
    accept = undefined,
    disabled = false,
    class: className = "",
    onchange,
    ...rest
  }: FileInputProps = $props();

  function forwardChange(event: FileInputEventWithTarget) {
    onchange?.(event);
  }
</script>

<input
  bind:this={element}
  class={cn("ui-file-input", className)}
  type="file"
  {accept}
  {disabled}
  onchange={forwardChange}
  {...rest}
/>

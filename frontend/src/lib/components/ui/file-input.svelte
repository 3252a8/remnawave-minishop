<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type FileInputProps = Omit<
    HTMLInputAttributes,
    "id" | "type" | "name" | "accept" | "disabled" | "class" | "onchange"
  > & {
    id?: string;
    element?: HTMLInputElement | null;
    name?: string;
    accept?: string | undefined;
    disabled?: boolean;
    class?: string;
    onchange?: HTMLInputAttributes["onchange"];
  };

  type FileInputEventWithTarget = Event & { currentTarget: EventTarget & HTMLInputElement };

  let {
    id = "",
    element = $bindable(null),
    name = undefined,
    accept = undefined,
    disabled = false,
    class: className = "",
    onchange,
    ...rest
  }: FileInputProps = $props();

  const fallbackId = `ui-file-input-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const inputId = $derived(id || fallbackId);

  function forwardChange(event: FileInputEventWithTarget) {
    onchange?.(event);
  }
</script>

<input
  id={inputId}
  bind:this={element}
  class={cn("ui-file-input", className)}
  type="file"
  {name}
  {accept}
  {disabled}
  onchange={forwardChange}
  {...rest}
/>

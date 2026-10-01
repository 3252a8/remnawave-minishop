<script lang="ts">
  import Button from "./button.svelte";
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  type FileInputProps = Omit<
    HTMLInputAttributes,
    "id" | "type" | "name" | "accept" | "disabled" | "class" | "onchange"
  > & {
    id?: string;
    element?: HTMLInputElement | null;
    buttonLabel?: string;
    emptyLabel?: string;
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
    buttonLabel = "",
    emptyLabel = "",
    name = undefined,
    accept = undefined,
    disabled = false,
    class: className = "",
    onchange,
    ...rest
  }: FileInputProps = $props();

  const fallbackId = `ui-file-input-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  const inputId = $derived(id || fallbackId);

  let selectedName = $state("");
  function forwardChange(event: FileInputEventWithTarget) {
    selectedName = Array.from(event.currentTarget.files || [])
      .map((file) => file.name)
      .join(", ");
    onchange?.(event);
  }
</script>

<input
  id={inputId}
  bind:this={element}
  class={cn("ui-file-input", buttonLabel && "sr-only", className)}
  type="file"
  {name}
  {accept}
  {disabled}
  onchange={forwardChange}
  {...rest}
  tabindex={buttonLabel ? -1 : rest.tabindex}
/>

{#if buttonLabel}
  <div class="ui-file-input-control">
    <Button
      size="sm"
      {disabled}
      aria-label={rest["aria-label"] ? `${buttonLabel}: ${rest["aria-label"]}` : buttonLabel}
      onclick={() => element?.click()}>{buttonLabel}</Button
    >
    <span title={selectedName}>{selectedName || emptyLabel}</span>
  </div>
{/if}

<style>
  .ui-file-input-control {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 5px 10px;
    min-height: 40px;
    box-sizing: border-box;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 8px;
    min-width: 0;
    color: var(--admin-muted, var(--muted));
    background: var(--admin-bg, var(--bg));
    font-size: 12px;
  }
  .ui-file-input-control span {
    min-width: 0;
    overflow-wrap: anywhere;
  }
</style>

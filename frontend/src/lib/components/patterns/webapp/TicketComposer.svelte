<script lang="ts">
  import { Send } from "$components/ui/icons.js";
  import { Button, Spinner } from "$components/ui/index.js";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import type { RichTextLabels } from "$lib/richtext/types";

  let {
    value = $bindable(""),
    labels,
    maxLength = 4000,
    disabled = false,
    sending = false,
    placeholder = "",
    sendLabel = "",
    onSend = () => {},
    onTyping = () => {},
  }: {
    value?: string;
    labels: RichTextLabels;
    maxLength?: number;
    disabled?: boolean;
    sending?: boolean;
    placeholder?: string;
    sendLabel?: string;
    onSend?: (value: string) => void | Promise<void>;
    onTyping?: (typing: boolean) => void;
  } = $props();

  // The server limits what the reader sees, so the counter measures the same
  // thing: formatting a sentence must not cost the customer characters.
  const length = $derived(wireTextLength(value, "html"));
  const overLimit = $derived(length > maxLength);
  const canSend = $derived(!disabled && !sending && length > 0 && !overLimit);

  function submit() {
    if (!canSend) return;
    onSend(value);
  }
</script>

<div class="ticket-composer">
  <RichTextEditor
    {value}
    onInput={(next) => (value = next)}
    {labels}
    {placeholder}
    {disabled}
    minHeight="96px"
    autolink
    onSubmit={submit}
    {onTyping}
  />
  <div class="ticket-composer-row">
    <small class:is-over={overLimit}>{length}/{maxLength}</small>
    <Button type="button" class="ticket-composer-send" disabled={!canSend} onclick={submit}>
      {#if sending}<Spinner size="sm" />{:else}<Send size={16} />{/if}
      <span>{sendLabel}</span>
    </Button>
  </div>
</div>

<style>
  .ticket-composer-row small.is-over {
    color: var(--danger);
  }
</style>

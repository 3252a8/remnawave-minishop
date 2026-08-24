<script lang="ts">
  import { Send } from "$components/ui/icons.js";
  import { Button, ImageAttachment, Spinner } from "$components/ui/index.js";
  import type { ImageAttachmentLabels } from "$components/ui/image-attachment.svelte";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import type { RichTextLabels } from "$lib/richtext/types";

  let {
    value = $bindable(""),
    image = $bindable(null),
    labels,
    imageLabels,
    maxLength = 4000,
    disabled = false,
    sending = false,
    placeholder = "",
    sendLabel = "",
    onSend = () => {},
    onTyping = () => {},
  }: {
    value?: string;
    image?: File | null;
    labels: RichTextLabels;
    imageLabels: ImageAttachmentLabels;
    maxLength?: number;
    disabled?: boolean;
    sending?: boolean;
    placeholder?: string;
    sendLabel?: string;
    onSend?: (value: string, image: File | null) => void | Promise<void>;
    onTyping?: (typing: boolean) => void;
  } = $props();

  // The server limits what the reader sees, so the counter measures the same
  // thing: formatting a sentence must not cost the customer characters.
  const length = $derived(wireTextLength(value, "html"));
  const overLimit = $derived(length > maxLength);
  const canSend = $derived(!disabled && !sending && (length > 0 || image !== null) && !overLimit);

  function submit() {
    if (!canSend) return;
    onSend(value, image);
  }
</script>

<div class="ticket-composer">
  <div class="ticket-composer-editor">
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
    <small class="ticket-composer-counter" class:is-over={overLimit}>{length}/{maxLength}</small>
  </div>
  <div class="ticket-composer-row">
    <ImageAttachment
      bind:file={image}
      labels={imageLabels}
      disabled={disabled || sending}
      compact
    />
    <Button type="button" class="ticket-composer-send" disabled={!canSend} onclick={submit}>
      {#if sending}<Spinner size="sm" />{:else}<Send size={16} />{/if}
      <span>{sendLabel}</span>
    </Button>
  </div>
</div>

<style>
  .ticket-composer-editor {
    position: relative;
    min-width: 0;
  }

  .ticket-composer-counter {
    position: absolute;
    right: 10px;
    bottom: 8px;
    z-index: 1;
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.01em;
    pointer-events: none;
  }

  .ticket-composer-editor :global(.rt-surface),
  .ticket-composer-editor :global(.rt-source) {
    padding-bottom: 26px;
  }

  .ticket-composer-counter.is-over {
    color: var(--danger);
  }
</style>

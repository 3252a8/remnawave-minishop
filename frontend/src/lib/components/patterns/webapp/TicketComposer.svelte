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
    sendDisabled = false,
    placeholder = "",
    sendLabel = "",
    showSendLabel = false,
    fillAvailable = false,
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
    sendDisabled?: boolean;
    placeholder?: string;
    sendLabel?: string;
    showSendLabel?: boolean;
    fillAvailable?: boolean;
    onSend?: (value: string, image: File | null) => void | Promise<void>;
    onTyping?: (typing: boolean) => void;
  } = $props();

  // Formatting does not consume the character budget: measure what the reader sees.
  const length = $derived(wireTextLength(value, "html"));
  const overLimit = $derived(length > maxLength);
  const nearLimit = $derived(length >= maxLength * 0.9);
  const canSend = $derived(
    !disabled && !sending && !sendDisabled && (length > 0 || image !== null) && !overLimit
  );

  function submit() {
    if (!canSend) return;
    onSend(value, image);
  }
</script>

<div
  class="ticket-composer"
  class:has-send-label={showSendLabel}
  class:fills-available-space={fillAvailable}
>
  <div class="ticket-composer-row">
    <ImageAttachment
      bind:file={image}
      labels={imageLabels}
      disabled={disabled || sending}
      iconOnly
      globalDropzone
    />
    <div class="ticket-composer-editor">
      <RichTextEditor
        {value}
        onInput={(next) => (value = next)}
        {labels}
        {placeholder}
        disabled={disabled || sending}
        showToolbar={false}
        minHeight={fillAvailable ? "0px" : showSendLabel ? "160px" : "48px"}
        autolink
        onSubmit={submit}
        {onTyping}
      />
    </div>
    <Button
      type="button"
      size="icon"
      class="ticket-composer-send"
      aria-label={sendLabel}
      title={sendLabel}
      disabled={!canSend}
      onclick={submit}
    >
      {#if sending}<Spinner size="sm" />{:else}<Send size={19} />{/if}
      {#if showSendLabel}<span>{sendLabel}</span>{/if}
    </Button>
    {#if nearLimit}
      <small class="ticket-composer-counter" class:is-over={overLimit} aria-live="polite">
        {length}/{maxLength}
      </small>
    {/if}
  </div>
</div>

<style>
  .ticket-composer {
    min-width: 0;
  }

  .ticket-composer-row {
    display: grid;
    grid-template-columns: 44px minmax(0, 1fr) 44px;
    align-items: end;
    gap: 6px;
  }

  .ticket-composer-editor {
    grid-column: 2;
    grid-row: 1;
    min-width: 0;
  }

  .ticket-composer-row :global(.message-image-attachment.is-icon-only) {
    display: contents;
  }

  .ticket-composer-row :global(.message-image-icon-trigger) {
    grid-column: 1;
    grid-row: 1;
    width: 44px;
    height: 48px;
    color: var(--muted);
    border-radius: 12px;
  }

  .ticket-composer-row :global(.message-image-preview),
  .ticket-composer-row :global(.message-image-error) {
    grid-column: 1 / -1;
    width: 100%;
    min-width: 0;
  }

  .ticket-composer-row :global(.message-image-preview) {
    grid-row: 2;
    border-style: solid;
  }

  .ticket-composer-row :global(.ticket-composer-send) {
    grid-column: 3;
    grid-row: 1;
    width: 44px;
    height: 48px;
    min-width: 0;
    padding: 0;
    border-radius: 14px;
  }

  .ticket-composer-editor :global(.rt-surface) {
    max-height: 160px;
    overflow-y: auto;
    scrollbar-width: thin;
    border: 0;
    border-radius: 0;
    background: transparent;
    padding: 11px 4px;
    transition: border-color 120ms ease;
  }

  .ticket-composer-editor :global(.rt-surface:focus-within) {
    border-color: var(--accent);
  }

  .ticket-composer-editor :global(.ProseMirror) {
    min-height: 24px;
    line-height: 1.5;
  }

  .ticket-composer-editor :global(.ProseMirror p:last-child) {
    margin-bottom: 0;
  }

  .ticket-composer-counter {
    grid-column: 2 / -1;
    justify-self: end;
    color: var(--muted);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .ticket-composer-counter.is-over {
    color: var(--danger);
  }

  .has-send-label .ticket-composer-row {
    grid-template-columns: 44px minmax(0, 1fr);
  }

  .has-send-label .ticket-composer-editor :global(.rt-surface) {
    max-height: 208px;
  }

  .has-send-label .ticket-composer-editor :global(.ProseMirror) {
    min-height: 136px;
  }

  .has-send-label :global(.ticket-composer-send) {
    grid-column: 1 / -1;
    grid-row: auto;
    width: 100%;
    margin-top: 4px;
  }

  @media (max-width: 390px) {
    .ticket-composer-row {
      grid-template-columns: 44px minmax(0, 1fr) 44px;
      gap: 4px;
    }

    .ticket-composer-row :global(.message-image-icon-trigger) {
      width: 44px;
    }

    .ticket-composer-row :global(.ticket-composer-send) {
      width: 44px;
    }

    .has-send-label .ticket-composer-row {
      grid-template-columns: 44px minmax(0, 1fr);
    }

    .has-send-label :global(.ticket-composer-send) {
      width: 100%;
    }
  }

  @media (max-width: 1023px) {
    .ticket-composer-editor :global(.ProseMirror) {
      font-size: 16px;
    }
  }

  .fills-available-space {
    height: 100%;
    min-height: 0;
    grid-template-rows: minmax(0, 1fr);
    overflow: hidden;
  }

  .fills-available-space .ticket-composer-row {
    min-height: 0;
    grid-template-columns: 44px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto auto auto auto;
    align-items: stretch;
    gap: 0 6px;
  }

  .fills-available-space .ticket-composer-editor {
    display: flex;
    min-height: 0;
    grid-column: 1 / -1;
  }

  .fills-available-space .ticket-composer-editor :global(.rt-editor) {
    width: 100%;
    min-height: 0;
  }

  .fills-available-space .ticket-composer-editor :global(.rt-surface) {
    flex: 1;
    min-height: 0;
    max-height: none;
  }

  .fills-available-space .ticket-composer-editor :global(.ProseMirror) {
    min-height: 100%;
  }

  .fills-available-space .ticket-composer-row :global(.message-image-preview) {
    grid-row: 2;
    margin-top: 8px;
  }

  .fills-available-space .ticket-composer-row :global(.message-image-error) {
    grid-row: 3;
    margin-top: 4px;
  }

  .fills-available-space .ticket-composer-counter {
    grid-row: 4;
    margin-top: 4px;
  }

  .fills-available-space .ticket-composer-row :global(.message-image-icon-trigger),
  .fills-available-space .ticket-composer-row :global(.ticket-composer-send) {
    grid-row: 5;
    margin-top: 8px;
  }

  .fills-available-space .ticket-composer-row :global(.ticket-composer-send) {
    grid-column: 2;
  }
</style>

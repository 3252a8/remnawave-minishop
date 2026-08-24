<script lang="ts">
  import { Upload, X } from "./icons.js";
  import Button from "./button.svelte";
  import FileInput from "./file-input.svelte";
  import {
    isAcceptedMessageImage,
    MESSAGE_IMAGE_ACCEPT,
    MESSAGE_IMAGE_MAX_BYTES,
  } from "$lib/messageImage";

  export type ImageAttachmentLabels = {
    drop: string;
    choose: string;
    upload?: string;
    remove: string;
    hint: string;
    invalidType: string;
    tooLarge: string;
    previewAlt: string;
  };

  let {
    file = $bindable(null),
    disabled = false,
    compact = false,
    globalDropzone = false,
    labels,
  }: {
    file?: File | null;
    disabled?: boolean;
    compact?: boolean;
    globalDropzone?: boolean;
    labels: ImageAttachmentLabels;
  } = $props();

  let inputElement = $state<HTMLInputElement | null>(null);
  let dragging = $state(false);
  let dragDepth = 0;
  let error = $state("");
  let previewUrl = $state("");

  $effect(() => {
    const selected = file;
    if (!selected) {
      previewUrl = "";
      return;
    }
    const url = URL.createObjectURL(selected);
    previewUrl = url;
    return () => URL.revokeObjectURL(url);
  });

  function selectFile(candidate: File | null): void {
    error = "";
    if (!candidate) return;
    if (!isAcceptedMessageImage(candidate)) {
      error = labels.invalidType;
      return;
    }
    if (candidate.size > MESSAGE_IMAGE_MAX_BYTES) {
      error = labels.tooLarge;
      return;
    }
    file = candidate;
  }

  function choose(): void {
    if (!disabled) inputElement?.click();
  }

  function onChange(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    selectFile(input.files?.[0] ?? null);
    input.value = "";
  }

  function onDragOver(event: DragEvent): void {
    if (globalDropzone) return;
    event.preventDefault();
    if (!disabled) dragging = true;
  }

  function onDragLeave(event: DragEvent): void {
    if (globalDropzone) return;
    if (
      !event.currentTarget ||
      !(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node)
    ) {
      dragging = false;
    }
  }

  function onDrop(event: DragEvent): void {
    if (globalDropzone) return;
    event.preventDefault();
    dragging = false;
    if (!disabled) selectFile(event.dataTransfer?.files?.[0] ?? null);
  }

  function remove(): void {
    if (disabled) return;
    file = null;
    error = "";
  }

  function hasDraggedFiles(event: DragEvent): boolean {
    return Array.from(event.dataTransfer?.types ?? []).includes("Files");
  }

  function onWindowDragEnter(event: DragEvent): void {
    if (!globalDropzone || disabled || !hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    dragging = true;
  }

  function onWindowDragOver(event: DragEvent): void {
    if (!globalDropzone || disabled || !hasDraggedFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    dragging = true;
  }

  function onWindowDragLeave(event: DragEvent): void {
    if (!globalDropzone || !dragging || !hasDraggedFiles(event)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dragging = false;
  }

  function onWindowDrop(event: DragEvent): void {
    if (!globalDropzone || disabled || !hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    dragging = false;
    selectFile(event.dataTransfer?.files?.[0] ?? null);
  }

  function resetWindowDrag(): void {
    dragDepth = 0;
    dragging = false;
  }
</script>

<svelte:window
  ondragenter={onWindowDragEnter}
  ondragover={onWindowDragOver}
  ondragleave={onWindowDragLeave}
  ondrop={onWindowDrop}
  ondragend={resetWindowDrag}
  onblur={resetWindowDrag}
/>

{#if globalDropzone && dragging}
  <div class="message-image-drag-overlay" aria-hidden="true"></div>
{/if}

<div
  class="message-image-attachment"
  class:is-dragging={dragging}
  class:is-compact={compact}
  role="group"
  ondragover={onDragOver}
  ondragleave={onDragLeave}
  ondrop={onDrop}
>
  <span class="message-image-input">
    <FileInput
      bind:element={inputElement}
      accept={MESSAGE_IMAGE_ACCEPT}
      {disabled}
      onchange={onChange}
    />
  </span>

  {#if file && previewUrl}
    <div class="message-image-preview">
      <img src={previewUrl} alt={labels.previewAlt} />
      <div class="message-image-meta">
        <strong>{file.name}</strong>
        <small>{Math.max(1, Math.ceil(file.size / 1024))} KB</small>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={labels.remove}
        title={labels.remove}
        {disabled}
        onclick={remove}
      >
        <X size={16} />
      </Button>
    </div>
  {:else}
    <button type="button" class="message-image-dropzone" {disabled} onclick={choose}>
      <Upload size={18} />
      {#if compact}
        <span>{labels.upload ?? labels.choose}</span>
      {:else}
        <span>{labels.drop} <strong>{labels.choose}</strong></span>
        <small>{labels.hint}</small>
      {/if}
    </button>
  {/if}

  {#if error}<small class="message-image-error" role="alert">{error}</small>{/if}
</div>

<style>
  .message-image-attachment {
    display: grid;
    gap: 6px;
  }

  .message-image-input {
    display: none;
  }

  .message-image-dropzone,
  .message-image-preview {
    width: 100%;
    min-height: 64px;
    border: 1px dashed var(--border, var(--admin-border, rgba(148, 163, 184, 0.34)));
    border-radius: 12px;
    background: var(--surface-soft, var(--admin-surface-muted, rgba(148, 163, 184, 0.08)));
  }

  .message-image-dropzone {
    display: grid;
    place-items: center;
    align-content: center;
    gap: 3px;
    padding: 10px 14px;
    color: var(--text-muted, var(--admin-text-muted, #8f9aaa));
    font: inherit;
    cursor: pointer;
  }

  .message-image-dropzone strong {
    color: var(--primary, var(--admin-accent, currentColor));
  }

  .message-image-dropzone small {
    font-size: 11px;
  }

  .message-image-dropzone:disabled {
    cursor: not-allowed;
    opacity: 0.58;
  }

  .message-image-attachment.is-dragging .message-image-dropzone,
  .message-image-attachment.is-dragging .message-image-preview {
    border-color: var(--primary, var(--admin-accent, #6d7cff));
    background: color-mix(in srgb, var(--primary, var(--admin-accent, #6d7cff)) 12%, transparent);
  }

  .message-image-preview {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px;
  }

  .message-image-preview img {
    width: 48px;
    height: 48px;
    flex: 0 0 auto;
    border-radius: 9px;
    object-fit: cover;
  }

  .message-image-meta {
    min-width: 0;
    display: grid;
    gap: 2px;
    margin-right: auto;
  }

  .message-image-meta strong {
    overflow: hidden;
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .message-image-meta small,
  .message-image-error {
    font-size: 11px;
    color: var(--text-muted, var(--admin-text-muted, #8f9aaa));
  }

  .message-image-error {
    color: var(--danger, var(--admin-danger, #ff5c5c));
  }

  .message-image-attachment.is-compact {
    min-width: 0;
  }

  .message-image-attachment.is-compact .message-image-dropzone {
    display: inline-flex;
    width: auto;
    height: var(--message-image-compact-height, 46px);
    min-height: var(--message-image-compact-height, 46px);
    align-items: center;
    justify-content: center;
    gap: 7px;
    border-style: solid;
    padding: 0 12px;
    white-space: nowrap;
  }

  .message-image-attachment.is-compact .message-image-preview {
    width: min(320px, 42vw);
    height: var(--message-image-compact-height, 46px);
    min-height: var(--message-image-compact-height, 46px);
    padding: 4px 6px;
  }

  .message-image-attachment.is-compact .message-image-preview img {
    width: 30px;
    height: 30px;
    border-radius: 7px;
  }

  .message-image-attachment.is-compact .message-image-meta strong {
    max-width: 180px;
  }

  .message-image-drag-overlay {
    position: fixed;
    z-index: 2147483000;
    inset: max(8px, env(safe-area-inset-top)) max(8px, env(safe-area-inset-right))
      max(8px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-left));
    border: 3px dashed var(--primary, var(--admin-accent, #6d7cff));
    border-radius: 18px;
    background: color-mix(in srgb, var(--primary, var(--admin-accent, #6d7cff)) 10%, transparent);
    box-shadow: inset 0 0 0 2px color-mix(in srgb, #fff 24%, transparent);
    pointer-events: none;
  }

  @media (max-width: 520px) {
    .message-image-attachment.is-compact {
      min-width: 0;
      flex: 1 1 auto;
    }

    .message-image-attachment.is-compact .message-image-dropzone,
    .message-image-attachment.is-compact .message-image-preview {
      width: 100%;
      max-width: none;
    }
  }
</style>

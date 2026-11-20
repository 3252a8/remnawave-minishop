<script lang="ts">
  import { Lock, Send, Sliders } from "$components/ui/icons.js";
  import { MediaQuery } from "svelte/reactivity";
  import { ImageAttachment, Spinner } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import MessageButtonsEditor from "$lib/admin/components/MessageButtonsEditor.svelte";
  import { getAdminApi } from "$lib/admin/context";
  import { createAdminEmojiPicker } from "$lib/admin/emojiPicker.svelte";
  import { adminRichTextLabels } from "$lib/admin/richTextLabels.js";
  import type { BroadcastButtonDraft } from "$lib/admin/stores/broadcastStore.svelte";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import type { MessageShortcodeInfo } from "$lib/richtext/editorSchema";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import type { RichTextQuickInsert } from "$lib/richtext/types";
  import EmojiPicker from "$lib/telegramEmoji/EmojiPicker.svelte";

  import type { TranslateFn } from "./types";

  type SelectOption = { value: string; label: string; disabled?: boolean; group?: string };

  type Props = {
    value?: string;
    images?: File[];
    buttons?: BroadcastButtonDraft[];
    internal?: boolean;
    sending?: boolean;
    maxLength?: number;
    at?: TranslateFn;
    shortcodes?: MessageShortcodeInfo[];
    promoOptions?: SelectOption[];
    promoOptionsLoading?: boolean;
    promoOptionsLoaded?: boolean;
    onRequestShortcodes?: () => void;
    onRequestPromoOptions?: () => void;
    onToggleInternal?: (checked: boolean) => void;
    onSend?: (body: string, images: File[]) => void;
    onTyping?: (typing: boolean) => void;
  };

  let {
    value = $bindable(""),
    images = $bindable([]),
    buttons = $bindable([]),
    internal = false,
    sending = false,
    maxLength = 4000,
    at = (key) => key,
    shortcodes = [],
    promoOptions = [],
    promoOptionsLoading = false,
    promoOptionsLoaded = false,
    onRequestShortcodes = () => {},
    onRequestPromoOptions = () => {},
    onToggleInternal = () => {},
    onSend = () => {},
    onTyping = () => {},
  }: Props = $props();

  const compact = new MediaQuery("max-width: 720px", false);
  let toolsOpen = $state(false);
  const showTools = $derived(!compact.current || toolsOpen);
  const toolsLabel = $derived(at("support_reply_tools", {}, "Reply tools"));
  const MAX_BUTTONS = 4;
  const api = getAdminApi();
  const emojiPicker = createAdminEmojiPicker();

  const labels = $derived(
    adminRichTextLabels(at, { linkPlaceholder: at("support_link_placeholder", {}, "https://...") })
  );
  // The limit the backend enforces counts what the customer reads, not the
  // tags around it, so the counter has to agree or it would forbid text the
  // server would have accepted.
  const length = $derived(wireTextLength(value, "html"));
  const overLimit = $derived(length > maxLength);
  const empty = $derived(length === 0);

  /**
   * Shortcuts into the shortcodes an admin reaches for in a conversation: the
   * two subscription links (the panel one the customer imports, and the Mini
   * App one) and the install guide. They resolve per recipient when the reply
   * is sent, so what is stored is the customer's own link.
   */
  const quickInserts: RichTextQuickInsert[] = $derived([
    {
      id: "config_link",
      label: at("support_insert_subscription_external", {}, "Subscription link"),
      description: at(
        "support_insert_subscription_external_hint",
        {},
        "The link the customer imports into their app"
      ),
      badge: at("broadcast_shortcode_panel_badge", {}, "panel"),
      content: { kind: "shortcode", name: "config_link" },
    },
    {
      id: "miniapp_link",
      label: at("support_insert_subscription_internal", {}, "Mini App link"),
      description: at(
        "support_insert_subscription_internal_hint",
        {},
        "Opens the customer's account in the Mini App"
      ),
      content: { kind: "shortcode", name: "miniapp_link" },
    },
    {
      id: "install_link",
      label: at("support_insert_install", {}, "Install guide"),
      description: at(
        "support_insert_install_hint",
        {},
        "Personal setup page for the customer's devices"
      ),
      content: { kind: "shortcode", name: "install_link" },
    },
  ]);

  function buttonTarget(button: BroadcastButtonDraft): string {
    if (button.kind === "url") return button.url.trim();
    if (button.kind === "webapp_section") return button.section.trim();
    return button.promoCode.trim();
  }

  const buttonsValid = $derived(buttons.every((button) => Boolean(buttonTarget(button))));
  let pasteTarget = $state<HTMLElement | null>(null);
  const canSend = $derived(!sending && (!empty || images.length > 0) && !overLimit && buttonsValid);

  export function focusEditor(): void {
    pasteTarget?.querySelector<HTMLElement>('.rt-source, [contenteditable="true"]')?.focus();
  }

  function submit(): void {
    if (!canSend) return;
    onSend(value, images);
  }

  function addButton(): void {
    if (buttons.length >= MAX_BUTTONS) return;
    buttons = [
      ...buttons,
      {
        id: Date.now() + buttons.length,
        kind: "url",
        label: "",
        url: "",
        promoCode: "",
        section: "",
      },
    ];
  }

  function updateButton(index: number, fields: Partial<BroadcastButtonDraft>): void {
    buttons = buttons.map((button, position) =>
      position === index ? { ...button, ...fields } : button
    );
  }

  function removeButton(index: number): void {
    buttons = buttons.filter((_, position) => position !== index);
  }

  function moveButton(from: number, to: number): void {
    if (from === to || from < 0 || to < 0 || from >= buttons.length || to >= buttons.length) return;
    const next = [...buttons];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    buttons = next;
  }
</script>

<div
  class="support-admin-composer"
  class:internal
  class:tools-open={toolsOpen}
  bind:this={pasteTarget}
>
  <div class="support-composer-mode">
    <strong
      >{internal
        ? at("support_note_audience", {}, "Only visible to staff")
        : at("support_public_reply", {}, "Reply to customer")}</strong
    >
    <div class="support-admin-note-toggle">
      <Switch.Root
        id="support-internal-note"
        aria-labelledby="support-internal-note-label"
        checked={internal}
        onCheckedChange={onToggleInternal}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <label id="support-internal-note-label" for="support-internal-note">
        <Lock size={14} />
        <span>{at("support_internal_note", {}, "Internal note")}</span>
      </label>
    </div>
  </div>
  <div class="support-composer-fields">
    <div class="support-admin-composer-editor">
      <RichTextEditor
        {value}
        onInput={(next) => (value = next)}
        {labels}
        {shortcodes}
        {onRequestShortcodes}
        {quickInserts}
        selectCustomEmoji={emojiPicker.select}
        loadCustomEmojiMedia={emojiPicker.loadMedia}
        placeholder={internal
          ? at("support_note_placeholder", {}, "Write an internal note")
          : at("support_reply_placeholder", {}, "Reply")}
        minHeight={compact.current ? "40px" : "120px"}
        showToolbar={showTools}
        autolink
        showSource
        onSubmit={submit}
        {onTyping}
      />
      <small class="support-admin-composer-counter" class:is-over={overLimit}>
        {length}/{maxLength}
      </small>
    </div>

    {#if !internal && showTools}
      <div class="support-admin-composer-buttons">
        <span class="admin-field-label">
          <span>{at("support_reply_buttons", {}, "Buttons")}</span>
          <small class="admin-muted">
            {at(
              "support_reply_buttons_hint",
              {},
              "Shown under the message in the chat and in the Telegram notification. A promo code activates in one tap."
            )}
          </small>
        </span>
        <MessageButtonsEditor
          {buttons}
          {at}
          max={MAX_BUTTONS}
          {promoOptions}
          {promoOptionsLoading}
          {promoOptionsLoaded}
          onAdd={addButton}
          onRemove={removeButton}
          onUpdate={updateButton}
          onReorder={moveButton}
          {onRequestPromoOptions}
        />
      </div>
    {/if}
  </div>
  <div class="support-admin-composer-row">
    <div class="support-admin-composer-actions">
      <ImageAttachment
        bind:files={images}
        multiple
        {pasteTarget}
        disabled={sending}
        compact
        iconOnly={compact.current}
        globalDropzone
        labels={{
          drop: at("message_image_drop", {}, "Drop an image here or"),
          choose: at("message_image_choose", {}, "choose a file"),
          upload: at("message_image_upload", {}, "Upload file"),
          remove: at("message_image_remove", {}, "Remove image"),
          hint: at("message_image_hint", {}, "HEIC, HEIF, JPEG, PNG or WebP, up to 8 MB"),
          invalidType: at(
            "message_image_invalid_type",
            {},
            "Choose a HEIC, HEIF, JPEG, PNG or WebP image"
          ),
          tooLarge: at("message_image_too_large", {}, "The image must be no larger than 8 MB"),
          previewAlt: at("message_image_preview_alt", {}, "Image preview"),
          tooMany: at("support_images_too_many"),
          totalTooLarge: at("support_images_too_large"),
          paste: at("support_images_paste_hint"),
        }}
      />
      {#if compact.current}
        <AdminButton
          class="support-tools-toggle"
          variant="ghost"
          aria-label={toolsLabel}
          title={toolsLabel}
          aria-expanded={toolsOpen}
          onclick={() => (toolsOpen = !toolsOpen)}
        >
          <Sliders size={16} />
        </AdminButton>
      {/if}
      <AdminButton variant="primary" disabled={!canSend} onclick={submit}>
        {#if sending}<Spinner size="sm" />{:else if internal}<Lock size={14} />{:else}<Send
            size={14}
          />{/if}
        {internal ? at("support_add_note", {}, "Add note") : at("send", {}, "Send")}
      </AdminButton>
    </div>
  </div>
</div>

<EmojiPicker
  open={emojiPicker.open}
  onOpenChange={emojiPicker.onOpenChange}
  onSelect={emojiPicker.onSelect}
  {at}
  {api}
/>

<style>
  .support-composer-mode {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 6px 12px;
    align-items: center;
    font-size: 13px;
  }

  .support-admin-composer.internal .support-composer-mode {
    color: var(--warning);
  }

  .support-admin-composer.internal .support-admin-composer-editor {
    border-inline-start: 3px solid var(--warning);
    padding-inline-start: 6px;
  }

  .support-composer-fields,
  .support-admin-composer-buttons {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .support-admin-composer-editor {
    position: relative;
    min-width: 0;
  }

  .support-admin-composer-counter {
    position: absolute;
    right: 10px;
    bottom: 8px;
    z-index: 1;
    font-size: 11px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--admin-text-muted, #9aa3b2);
    pointer-events: none;
  }

  .support-admin-composer-editor :global(.rt-surface),
  .support-admin-composer-editor :global(.rt-source) {
    padding-bottom: 26px;
  }

  .support-admin-composer-counter.is-over {
    color: var(--admin-danger, #ff5c5c);
  }

  .support-admin-composer-actions {
    --message-image-compact-height: 36px;

    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: start;
    gap: 6px 10px;
    flex: 1;
    min-width: 0;
  }

  .support-admin-composer-actions :global(.message-image-attachment) {
    display: contents;
  }

  .support-admin-composer-actions :global(.message-image-dropzone) {
    grid-area: 1 / 1;
    width: auto;
  }

  .support-admin-composer-actions :global(.admin-btn-primary) {
    grid-area: 1 / 3;
  }

  .support-admin-composer-actions :global(.message-image-paste-hint) {
    grid-area: 1 / 2;
    align-self: center;
  }

  .support-admin-composer-actions :global(.message-image-previews),
  .support-admin-composer-actions :global(.message-image-error) {
    grid-column: 1 / -1;
  }

  @media (max-width: 720px) {
    .support-composer-fields {
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
    }

    .support-composer-mode {
      font-size: 12px;
    }

    .support-composer-mode .support-admin-note-toggle {
      padding: 2px 4px;
      border: 0;
      background: transparent;
    }

    .support-composer-mode .support-admin-note-toggle label {
      font-size: 12px;
    }

    .support-admin-composer-editor :global(.rt-surface),
    .support-admin-composer-editor :global(.rt-source) {
      box-sizing: border-box;
      min-height: 40px;
      max-height: clamp(62px, calc(var(--support-viewport-height, 100dvh) * 0.22), 144px);
      padding: 7px 10px;
      overflow-y: auto;
    }

    .support-admin-composer-editor :global(.rt-surface .ProseMirror) {
      min-height: 24px;
      padding-inline-end: 42px;
    }

    .support-admin-composer-counter {
      right: 8px;
      bottom: 8px;
      background: var(--admin-surface-2);
    }

    .support-admin-composer-actions {
      grid-template-columns: auto auto 1fr auto;
    }

    .support-admin-composer-actions :global(.message-image-icon-trigger) {
      grid-area: 1 / 1;
      width: 36px;
      height: 36px;
    }

    .support-admin-composer-actions :global(.message-image-previews) {
      max-height: clamp(46px, calc(var(--support-viewport-height, 100dvh) * 0.14), 100px);
      overflow-y: auto;
    }

    .support-admin-composer-actions :global(.support-tools-toggle) {
      grid-area: 1 / 2;
    }

    .support-admin-composer-actions :global(.admin-btn-primary) {
      grid-area: 1 / 4;
    }

    .support-admin-composer-actions :global(.message-image-paste-hint) {
      display: none;
    }
  }

  @media (max-width: 520px) {
    .support-admin-composer-actions {
      flex-basis: 100%;
    }

    .support-admin-composer-actions :global(.message-image-paste-hint) {
      grid-area: 2 / 1 / auto / -1;
    }
  }
</style>

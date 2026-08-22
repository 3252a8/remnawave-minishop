<script lang="ts">
  import { Lock, Send } from "$components/ui/icons.js";
  import { ImageAttachment, Spinner } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import MessageButtonsEditor from "$lib/admin/components/MessageButtonsEditor.svelte";
  import { adminRichTextLabels } from "$lib/admin/richTextLabels.js";
  import type { BroadcastButtonDraft } from "$lib/admin/stores/broadcastStore.svelte";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import type { MessageShortcodeInfo } from "$lib/richtext/editorSchema";
  import { wireTextLength } from "$lib/richtext/telegramHtml";
  import type { RichTextQuickInsert } from "$lib/richtext/types";

  import type { TranslateFn } from "./types";

  type SelectOption = { value: string; label: string; disabled?: boolean; group?: string };

  type Props = {
    value?: string;
    image?: File | null;
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
    onSend?: (body: string, image: File | null) => void;
    onTyping?: (typing: boolean) => void;
  };

  let {
    value = $bindable(""),
    image = $bindable(null),
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

  const MAX_BUTTONS = 4;

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
  const canSend = $derived(!sending && (!empty || image !== null) && !overLimit && buttonsValid);

  // A note never reaches the customer, so the buttons it would have carried are
  // dropped rather than silently sent with the next reply.
  $effect(() => {
    if (internal && buttons.length) buttons = [];
  });

  function submit(): void {
    if (!canSend) return;
    onSend(value, image);
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

<div class="support-admin-composer">
  <RichTextEditor
    {value}
    onInput={(next) => (value = next)}
    {labels}
    {shortcodes}
    {onRequestShortcodes}
    {quickInserts}
    placeholder={at("support_reply_placeholder", {}, "Reply")}
    minHeight="120px"
    autolink
    showSource
    onSubmit={submit}
    {onTyping}
  />

  <ImageAttachment
    bind:file={image}
    disabled={sending}
    labels={{
      drop: at("message_image_drop", {}, "Drop an image here or"),
      choose: at("message_image_choose", {}, "choose a file"),
      remove: at("message_image_remove", {}, "Remove image"),
      hint: at("message_image_hint", {}, "JPEG, PNG or WebP, up to 8 MB"),
      invalidType: at("message_image_invalid_type", {}, "Choose a JPEG, PNG or WebP image"),
      tooLarge: at("message_image_too_large", {}, "The image must be no larger than 8 MB"),
      previewAlt: at("message_image_preview_alt", {}, "Image preview"),
    }}
  />

  {#if !internal}
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

  <div class="support-admin-composer-row">
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

    <small class="support-admin-composer-counter" class:is-over={overLimit}>
      {length}/{maxLength}
    </small>

    <AdminButton variant="primary" disabled={!canSend} onclick={submit}>
      {#if sending}<Spinner size="sm" />{:else}<Send size={14} />{/if}
      {at("send", {}, "Send")}
    </AdminButton>
  </div>
</div>

<style>
  .support-admin-composer-buttons {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .support-admin-composer-counter {
    margin-left: auto;
    font-size: 11px;
    color: var(--admin-text-muted, #9aa3b2);
  }

  .support-admin-composer-counter.is-over {
    color: var(--admin-danger, #ff5c5c);
  }
</style>

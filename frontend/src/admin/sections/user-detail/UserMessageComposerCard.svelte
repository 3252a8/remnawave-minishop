<script lang="ts">
  import { AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { Checkbox, ImageAttachment, Input } from "$components/ui/index.js";
  import { Send } from "$components/ui/icons.js";
  import MessageButtonsEditor from "$lib/admin/components/MessageButtonsEditor.svelte";
  import MessageComposer from "$lib/admin/components/MessageComposer.svelte";
  import { getBroadcastStore } from "$lib/admin/context";
  import type { BroadcastButtonDraft } from "$lib/admin/stores/broadcastStore.svelte";

  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    userId,
    hasTelegram = false,
    hasEmail = false,
  }: {
    at: TranslateFn;
    userId: number | null;
    hasTelegram?: boolean;
    hasEmail?: boolean;
  } = $props();

  const MAX_BUTTONS = 4;
  // Shortcodes are advertised by the backend and shared with the broadcast
  // screen, so the composer offers the same set in both places.
  const broadcastStore = getBroadcastStore();
  const shortcodes = $derived(broadcastStore.broadcastShortcodes);

  let text = $state("");
  let image = $state<File | null>(null);
  let emailSubject = $state("");
  let telegramEnabled = $state(false);
  let emailEnabled = $state(false);
  let buttons = $state<BroadcastButtonDraft[]>([]);
  let busy = $state(false);
  let result = $state<{ kind: "ok" | "error"; message: string } | null>(null);

  const channels = $derived(
    [telegramEnabled ? "telegram" : "", emailEnabled ? "email" : ""].filter(Boolean)
  );
  /** The field a button kind actually needs filled in before it can be sent. */
  function buttonTarget(button: BroadcastButtonDraft): string {
    if (button.kind === "url") return button.url.trim();
    if (button.kind === "webapp_section") return button.section.trim();
    return button.promoCode.trim();
  }

  const buttonsValid = $derived(
    buttons.every((button) => button.label.trim() && Boolean(buttonTarget(button)))
  );
  const canSend = $derived(
    !busy && userId !== null && Boolean(text.trim() || image) && channels.length > 0 && buttonsValid
  );

  // Unavailable delivery channels stay off instead of reporting a successful
  // zero-recipient send. Email becomes the default for email-only accounts.
  $effect(() => {
    telegramEnabled = hasTelegram;
    emailEnabled = !hasTelegram && hasEmail;
  });

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

  async function send(): Promise<void> {
    if (userId === null) return;
    busy = true;
    result = null;
    const error = await broadcastStore.sendToUser({
      userId,
      text,
      channels,
      emailSubject,
      buttons,
      image,
    });
    if (error === null) {
      text = "";
      emailSubject = "";
      buttons = [];
      image = null;
      result = { kind: "ok", message: at("user_message_sent", {}, "Message sent") };
    } else {
      result = { kind: "error", message: error };
    }
    busy = false;
  }
</script>

<section class="admin-user-action-sheet admin-user-action-sheet--message">
  <AdminSectionHeader
    title={at("user_message_title", {}, "Send a message")}
    description={at(
      "user_message_hint",
      {},
      "Rich text with shortcodes and buttons, delivered to Telegram and email."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-message-body">
    <div class="admin-user-message-main">
      <div class="admin-field-label">
        <span>{at("broadcast_label_text", {}, "Message text")}</span>
        <MessageComposer
          value={text}
          onInput={(next) => (text = next)}
          {shortcodes}
          onRequestShortcodes={broadcastStore.loadShortcodes}
          {at}
          placeholder={at("user_placeholder_msg", {}, "Message text")}
        />
      </div>
      <div class="admin-field-label">
        <span>{at("broadcast_buttons_label", {}, "Buttons")}</span>
        <small class="admin-muted"
          >{at(
            "broadcast_buttons_hint",
            {},
            "Up to 4 buttons: inline buttons in Telegram, link buttons in email. Promo codes activate in one tap."
          )}</small
        >
        <MessageButtonsEditor
          {buttons}
          {at}
          max={MAX_BUTTONS}
          promoOptions={broadcastStore.broadcastPromoOptions}
          promoOptionsLoading={broadcastStore.broadcastPromoOptionsLoading}
          promoOptionsLoaded={broadcastStore.broadcastPromoOptionsLoaded}
          onAdd={addButton}
          onRemove={removeButton}
          onUpdate={updateButton}
          onReorder={moveButton}
          onRequestPromoOptions={broadcastStore.loadPromoOptions}
        />
      </div>
    </div>
    <div class="admin-user-message-options">
      <div class="admin-field-label">
        <span>{at("user_message_delivery", {}, "Delivery channels")}</span>
        <div class="admin-user-message-channels">
          <label class="admin-check" class:is-disabled={!hasTelegram}>
            <Checkbox
              id="user-message-channel-telegram"
              name="user-message-channel-telegram"
              ariaLabel={at("broadcast_channel_telegram", {}, "Telegram")}
              bind:checked={telegramEnabled}
              disabled={busy || !hasTelegram}
            />
            {at("broadcast_channel_telegram", {}, "Telegram")}
            {#if !hasTelegram}<small class="admin-muted"
                >{at("user_message_no_telegram", {}, "no linked account")}</small
              >{/if}
          </label>
          <label class="admin-check" class:is-disabled={!hasEmail}>
            <Checkbox
              id="user-message-channel-email"
              name="user-message-channel-email"
              ariaLabel={at("broadcast_channel_email", {}, "Email")}
              bind:checked={emailEnabled}
              disabled={busy || !hasEmail}
            />
            {at("broadcast_channel_email", {}, "Email")}
            {#if !hasEmail}<small class="admin-muted"
                >{at("user_message_no_email", {}, "no linked address")}</small
              >{/if}
          </label>
        </div>
        {#if emailEnabled}
          <label class="admin-field-label">
            <span>{at("broadcast_email_subject_label", {}, "Email subject")}</span>
            <Input
              class="input"
              type="text"
              value={emailSubject}
              placeholder={at("broadcast_email_subject_label", {}, "Email subject")}
              aria-label={at("broadcast_email_subject_label", {}, "Email subject")}
              oninput={(event) => (emailSubject = (event.currentTarget as HTMLInputElement).value)}
            />
          </label>
        {/if}
      </div>
      <div class="admin-field-label">
        <span>{at("message_image_label", {}, "Image")}</span>
        <ImageAttachment
          bind:file={image}
          disabled={busy}
          labels={{
            drop: at("message_image_drop", {}, "Drop an image here or"),
            choose: at("message_image_choose", {}, "choose a file"),
            remove: at("message_image_remove", {}, "Remove image"),
            hint: at("message_image_hint", {}, "HEIC, HEIF, JPEG, PNG or WebP, up to 8 MB"),
            invalidType: at(
              "message_image_invalid_type",
              {},
              "Choose a HEIC, HEIF, JPEG, PNG or WebP image"
            ),
            tooLarge: at("message_image_too_large", {}, "The image must be no larger than 8 MB"),
            previewAlt: at("message_image_preview_alt", {}, "Image preview"),
          }}
        />
      </div>
    </div>
    <div class="admin-user-message-footer">
      <AdminButton
        variant="primary"
        data-admin-action="send-user-message"
        disabled={!canSend}
        onclick={() => void send()}
      >
        <Send size={14} />
        {busy ? at("user_message_sending", {}, "Sending…") : at("btn_send_msg", {}, "Send message")}
      </AdminButton>
      {#if result}<p class={result.kind === "ok" ? "admin-success" : "admin-error"} role="status">
          {result.message}
        </p>{/if}
    </div>
  </div>
</section>

<style>
  .admin-user-action-sheet--message {
    margin: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    overflow: visible;
  }
  .admin-user-action-sheet--message :global(.admin-dashboard-section-head) {
    padding: 0 0 14px;
  }
  .admin-user-message-body {
    display: grid;
    min-width: 0;
    gap: 20px;
    padding: 16px 0 0;
  }
  .admin-user-message-main,
  .admin-user-message-options {
    display: grid;
    align-content: start;
    gap: 18px;
    min-width: 0;
  }
  .admin-user-message-footer {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    min-width: 0;
    padding-top: 16px;
    border-top: 1px solid var(--admin-border);
  }
  .admin-user-message-footer p {
    margin: 0;
  }
  .admin-user-message-channels {
    display: grid;
    gap: 12px;
  }
  .admin-user-message-channels .is-disabled {
    opacity: 0.6;
  }
  .admin-user-message-channels small {
    font-size: 11px;
  }
  @container user-detail (min-width: 960px) {
    .admin-user-message-body {
      grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
      gap: 20px 28px;
    }
    .admin-user-message-options {
      border-left: 1px solid var(--admin-border);
      padding-left: 24px;
    }
    .admin-user-message-footer {
      grid-column: 1 / -1;
    }
  }
  @media (max-width: 640px) {
    .admin-user-message-footer :global(.admin-btn) {
      width: 100%;
    }
  }
</style>

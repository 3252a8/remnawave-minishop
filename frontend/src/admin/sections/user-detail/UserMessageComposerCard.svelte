<script lang="ts">
  import { AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { ImageAttachment, Input } from "$components/ui/index.js";
  import { Send } from "$components/ui/icons.js";
  import MessageButtonsEditor from "$lib/admin/components/MessageButtonsEditor.svelte";
  import MessageComposer from "$lib/admin/components/MessageComposer.svelte";
  import { getBroadcastStore } from "$lib/admin/context";
  import type { BroadcastButtonDraft } from "$lib/admin/stores/broadcastStore.svelte";

  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    userId,
    hasEmail = false,
  }: {
    at: TranslateFn;
    userId: number | null;
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
  let telegramEnabled = $state(true);
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

  // An email-only draft is impossible for a customer with no linked address,
  // so the toggle stays off and disabled rather than failing on send.
  $effect(() => {
    if (!hasEmail && emailEnabled) emailEnabled = false;
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
  <div class="admin-user-action-sheet-body">
    <MessageComposer
      value={text}
      onInput={(next) => (text = next)}
      {shortcodes}
      onRequestShortcodes={broadcastStore.loadShortcodes}
      {at}
      placeholder={at("user_placeholder_msg", {}, "Message text")}
    />

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

    <div class="admin-user-message-channels">
      <label class="admin-check">
        <input
          type="checkbox"
          id="user-message-channel-telegram"
          name="user-message-channel-telegram"
          bind:checked={telegramEnabled}
        />
        {at("broadcast_channel_telegram", {}, "Telegram")}
      </label>
      <label class="admin-check" class:is-disabled={!hasEmail}>
        <input
          type="checkbox"
          id="user-message-channel-email"
          name="user-message-channel-email"
          bind:checked={emailEnabled}
          disabled={!hasEmail}
        />
        {at("broadcast_channel_email", {}, "Email")}
        {#if !hasEmail}
          <small class="admin-muted">{at("user_message_no_email", {}, "no linked address")}</small>
        {/if}
      </label>
    </div>

    {#if emailEnabled}
      <Input
        class="input"
        type="text"
        value={emailSubject}
        placeholder={at("broadcast_email_subject_label", {}, "Email subject")}
        aria-label={at("broadcast_email_subject_label", {}, "Email subject")}
        oninput={(event) => (emailSubject = (event.currentTarget as HTMLInputElement).value)}
      />
    {/if}

    <div class="admin-field-label">
      <span>{at("broadcast_buttons_label", {}, "Buttons")}</span>
      <small class="admin-muted">
        {at(
          "broadcast_buttons_hint",
          {},
          "Up to 4 buttons: inline buttons in Telegram, link buttons in email. Promo codes activate in one tap."
        )}
      </small>
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

    {#if result}
      <p class={result.kind === "ok" ? "admin-success" : "admin-error"} role="status">
        {result.message}
      </p>
    {/if}

    <div class="admin-message-actions">
      <AdminButton
        variant="primary"
        data-admin-action="send-user-message"
        disabled={!canSend}
        onclick={() => void send()}
      >
        <Send size={14} />
        {busy ? at("user_message_sending", {}, "Sending…") : at("btn_send_msg", {}, "Send message")}
      </AdminButton>
    </div>
  </div>
</section>

<style>
  .admin-user-message-channels {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: center;
  }

  .admin-user-message-channels .is-disabled {
    opacity: 0.6;
  }

  .admin-user-message-channels small {
    font-size: 11px;
  }
</style>

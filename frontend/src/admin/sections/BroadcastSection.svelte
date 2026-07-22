<script lang="ts">
  import { getBroadcastStore } from "$lib/admin/context";
  import { Checkbox, Input, Sortable } from "$components/ui/index.js";
  import { Plus, Send, Trash2 } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import BroadcastEditor from "$lib/admin/components/BroadcastEditor.svelte";
  import { previewHtmlFromWire } from "$lib/admin/telegramHtml";
  import type {
    BroadcastButtonDraft,
    BroadcastButtonKind,
  } from "$lib/admin/stores/broadcastStore.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at }: { at: TranslateFn } = $props();
  const broadcastStore = getBroadcastStore();

  // Sample values for the client-side live preview only; the server preview
  // uses real recipient data.
  const PREVIEW_SAMPLES: Record<string, string> = {
    first_name: "Alex",
    last_name: "Petrov",
    username: "@alex",
    user_id: "100245",
    email: "alex@example.com",
    end_date: "2030-05-01",
    days_left: "42",
    subscription_status: "active",
    tariff_name: "Premium",
    tariff_price: "299 RUB",
    traffic_used: "30",
    traffic_limit: "100",
    traffic_left: "70",
    install_link: "https://app.example/s/demo",
    miniapp_link: "https://app.example/",
    config_link: "happ://crypt4/demo",
    referral_code: "AB12CD",
    referral_bot_link: "https://t.me/demo_bot?start=ref_uAB12CD",
    referral_webapp_link: "https://app.example/?ref=uAB12CD",
  };

  const previewBusy = $derived(Boolean(broadcastStore.broadcastPreviewBusy));
  const previewResult = $derived(broadcastStore.broadcastPreviewResult);
  const clientPreviewHtml = $derived(
    broadcastStore.broadcastText.trim()
      ? previewHtmlFromWire(broadcastStore.broadcastText, PREVIEW_SAMPLES)
      : ""
  );

  const broadcastTarget = $derived(broadcastStore.broadcastTarget);
  const broadcastTargetError = $derived(broadcastStore.broadcastTargetError);
  const broadcastText = $derived(broadcastStore.broadcastText);
  const broadcastBusy = $derived(broadcastStore.broadcastBusy);
  const broadcastResult = $derived(broadcastStore.broadcastResult);
  const broadcastCounts = $derived(broadcastStore.broadcastCounts as Record<string, number> | null);
  const broadcastCountsLoading = $derived(Boolean(broadcastStore.broadcastCountsLoading));
  const telegramEnabled = $derived(broadcastStore.broadcastTelegramEnabled);
  const emailEnabled = $derived(broadcastStore.broadcastEmailEnabled);
  const emailAvailable = $derived(broadcastStore.broadcastEmailAvailable);
  const emailAvailabilityKnown = $derived(broadcastStore.broadcastEmailAvailabilityKnown);
  const emailSelectable = $derived(!emailAvailabilityKnown || emailAvailable);
  const emailSubject = $derived(broadcastStore.broadcastEmailSubject);
  const broadcastButtons = $derived(broadcastStore.broadcastButtons);
  const promoOptions = $derived(broadcastStore.broadcastPromoOptions);
  const promoOptionsLoading = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoading));
  const promoOptionsLoaded = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoaded));
  const hasPromoButtons = $derived(broadcastButtons.some((button) => button.kind !== "url"));
  const submitEnabled = $derived(broadcastStore.canSubmit());
  const handleTargetChange = (value: string) => {
    broadcastStore.updateField({ broadcastTarget: value, broadcastTargetError: null });
    writeTargetToRoute(value);
  };

  function routeTarget(): string {
    if (typeof window === "undefined") return "";
    return String(new URLSearchParams(window.location.search).get("broadcast_target") || "")
      .trim()
      .toLowerCase();
  }

  function writeTargetToRoute(target: string | null): void {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    const query = new URLSearchParams(window.location.search);
    if (target) query.set("broadcast_target", target);
    else query.delete("broadcast_target");
    const search = query.toString();
    const nextUrl = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (nextUrl !== currentUrl) window.history.replaceState(window.history.state, "", nextUrl);
  }

  const broadcastTargetOptions = $derived(broadcastStore.BROADCAST_TARGET_OPTIONS);

  const buttonKindOptions = $derived([
    { value: "url", label: at("broadcast_button_kind_url", {}, "Link") },
    {
      value: "promo_bot",
      label: at("broadcast_button_kind_promo_bot", {}, "Promo code — in bot"),
    },
    {
      value: "promo_webapp",
      label: at("broadcast_button_kind_promo_webapp", {}, "Promo code — in web app"),
    },
  ]);

  // Append the resolved audience size to each option once counts are loaded.
  const targetOptions = $derived(
    broadcastTargetOptions.map((option) => {
      const count = broadcastCounts?.[option.value];
      if (count != null) return { ...option, label: `${option.label} (${count})` };
      if (broadcastCountsLoading) return { ...option, label: `${option.label} (...)` };
      return option;
    })
  );

  onMount(() => {
    const requestedTarget = routeTarget();
    if (requestedTarget) {
      // Set before discovery completes so a plugin audience is retained when
      // the counts response supplies the dynamic target catalog.
      broadcastStore.updateField({ broadcastTarget: requestedTarget, broadcastTargetError: null });
    }
    void broadcastStore.loadCounts().then(() => {
      if (!requestedTarget) return;
      const available = broadcastStore.BROADCAST_TARGET_OPTIONS.some(
        (option) => option.value === requestedTarget
      );
      if (available) return;
      broadcastStore.updateField({
        broadcastTarget: "all",
        broadcastTargetError: "broadcast_target_unavailable",
      });
      writeTargetToRoute(null);
    });
    if (broadcastStore.broadcastButtons.some((button) => button.kind !== "url")) {
      broadcastStore.loadPromoOptions();
    }
  });
</script>

<div class="admin-card">
  <header class="admin-card-head">
    <h3>{at("broadcast_title", {}, "Broadcast")}</h3>
    <small>{at("broadcast_subtitle", {}, "Delivery via message queue")}</small>
  </header>
  <div class="admin-card-body">
    <div class="admin-form">
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_audience", {}, "Audience")}</span>
        <AdminSelect
          value={broadcastTarget}
          items={targetOptions}
          ariaLabel={at("broadcast_label_audience", {}, "Audience")}
          onValueChange={handleTargetChange}
        />
        {#if broadcastTargetError}
          <small class="admin-field-error">
            {at("broadcast_target_unavailable", {}, "The requested audience is unavailable")}
          </small>
        {/if}
      </Label.Root>
      <div class="admin-field-label">
        <span>{at("broadcast_channels_label", {}, "Delivery channels")}</span>
        <div class="broadcast-channels">
          <label class="broadcast-channel">
            <Checkbox
              checked={telegramEnabled}
              ariaLabel={at("broadcast_channel_telegram", {}, "Telegram")}
              onCheckedChange={(checked) =>
                broadcastStore.updateField({ broadcastTelegramEnabled: checked })}
            />
            <span>{at("broadcast_channel_telegram", {}, "Telegram")}</span>
          </label>
          <label class="broadcast-channel">
            <Checkbox
              checked={emailEnabled && emailSelectable}
              disabled={emailAvailabilityKnown && !emailAvailable}
              ariaLabel={at("broadcast_channel_email", {}, "Email")}
              onCheckedChange={(checked) =>
                broadcastStore.updateField({ broadcastEmailEnabled: checked })}
            />
            <span>{at("broadcast_channel_email", {}, "Email")}</span>
          </label>
        </div>
        {#if emailAvailabilityKnown && !emailAvailable}
          <small class="admin-muted"
            >{at(
              "broadcast_email_unavailable_hint",
              {},
              "Email channel unavailable: SMTP is not configured"
            )}</small
          >
        {/if}
      </div>
      {#if emailEnabled && emailSelectable}
        <Label.Root class="admin-field-label">
          <span>{at("broadcast_email_subject_label", {}, "Email subject")}</span>
          <Input
            value={emailSubject}
            placeholder={at(
              "broadcast_email_subject_placeholder",
              {},
              "Leave empty to use the default subject"
            )}
            oninput={(e) =>
              broadcastStore.updateField({
                broadcastEmailSubject: (e.currentTarget as HTMLInputElement).value,
              })}
          />
        </Label.Root>
      {/if}
      <div class="admin-field-label">
        <span>{at("broadcast_label_text", {}, "Message Text")}</span>
        <small>{at("broadcast_hint_text", {}, "Telegram HTML formatting supported")}</small>
        <BroadcastEditor
          value={broadcastText}
          onInput={(next) => broadcastStore.updateField({ broadcastText: next })}
          shortcodes={broadcastStore.broadcastShortcodes}
          onRequestShortcodes={broadcastStore.loadShortcodes}
          {at}
          placeholder={at("broadcast_editor_placeholder", {}, "Broadcast text...")}
        />
      </div>

      <div class="admin-field-label">
        <div class="broadcast-preview-head">
          <span>{at("broadcast_preview_title", {}, "Preview")}</span>
          <div class="broadcast-preview-actions">
            <AdminButton
              size="sm"
              variant="ghost"
              disabled={previewBusy || !broadcastText.trim()}
              onclick={() => broadcastStore.sendPreview("render")}
            >
              {at("broadcast_preview_render", {}, "Refresh with data")}
            </AdminButton>
            <AdminButton
              size="sm"
              variant="ghost"
              disabled={previewBusy || !broadcastText.trim()}
              onclick={() => broadcastStore.sendPreview("send_telegram")}
            >
              {at("broadcast_preview_send", {}, "Send to my Telegram")}
            </AdminButton>
          </div>
        </div>
        {#if clientPreviewHtml}
          <!-- previewHtmlFromWire escapes all text and emits only whitelisted tags -->
          <div class="broadcast-preview">{@html clientPreviewHtml}</div>
        {:else}
          <div class="broadcast-preview broadcast-preview-empty">
            {at("broadcast_preview_placeholder", {}, "The message preview will appear here")}
          </div>
        {/if}
        {#if previewResult}
          {#if previewResult.unknownShortcodes.length}
            <small class="admin-muted broadcast-preview-warn"
              >{at("broadcast_preview_unknown", {}, "Unknown shortcodes")}:
              {previewResult.unknownShortcodes.join(", ")}</small
            >
          {/if}
          <small class="admin-muted"
            >{at("broadcast_preview_length", {}, "Length")}: {previewResult.length}</small
          >
        {/if}
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
        <div class="admin-row-editor">
          <Sortable
            items={broadcastButtons}
            class="admin-row-editor-line admin-row-editor-broadcast"
            getKey={(button: BroadcastButtonDraft) => button.id}
            handleLabel={at("broadcast_button_reorder", {}, "Drag to reorder buttons")}
            onReorder={broadcastStore.moveButton}
          >
            {#snippet children(button: BroadcastButtonDraft, index: number)}
              <AdminSelect
                value={button.kind}
                items={buttonKindOptions}
                ariaLabel={at("broadcast_buttons_label", {}, "Buttons")}
                onValueChange={(value) =>
                  broadcastStore.updateButton(index, { kind: value as BroadcastButtonKind })}
              />
              <Input
                class="input"
                value={button.label}
                maxlength={64}
                placeholder={at("broadcast_button_label_placeholder", {}, "Button label")}
                oninput={(e) =>
                  broadcastStore.updateButton(index, {
                    label: (e.currentTarget as HTMLInputElement).value,
                  })}
              />
              {#if button.kind === "url"}
                <Input
                  class="input"
                  value={button.url}
                  placeholder={at("broadcast_button_url_placeholder", {}, "https://…")}
                  oninput={(e) =>
                    broadcastStore.updateButton(index, {
                      url: (e.currentTarget as HTMLInputElement).value,
                    })}
                />
              {:else}
                <AdminSelect
                  value={button.promoCode}
                  items={promoOptions}
                  placeholder={promoOptionsLoading
                    ? at("broadcast_button_promo_loading", {}, "Loading codes...")
                    : at("broadcast_button_promo_select", {}, "Select a code")}
                  ariaLabel={at("broadcast_button_promo_select", {}, "Select a code")}
                  onValueChange={(value) =>
                    broadcastStore.updateButton(index, { promoCode: value })}
                />
              {/if}
              <AdminButton
                size="sm"
                variant="danger"
                aria-label={at("broadcast_button_remove", {}, "Remove button")}
                onclick={() => broadcastStore.removeButton(index)}
              >
                <Trash2 size={13} />
              </AdminButton>
            {/snippet}
          </Sortable>
        </div>
        {#if hasPromoButtons && promoOptionsLoaded && !promoOptions.length}
          <small class="admin-muted"
            >{at(
              "broadcast_no_promos_hint",
              {},
              "No active codes — create one in the Promo codes section first"
            )}</small
          >
        {/if}
        {#if broadcastButtons.length < broadcastStore.MAX_BROADCAST_BUTTONS}
          <div>
            <AdminButton variant="ghost" onclick={broadcastStore.addButton}>
              <Plus size={14} />
              {at("broadcast_button_add", {}, "Add button")}
            </AdminButton>
          </div>
        {/if}
      </div>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <AdminButton
          variant="primary"
          onclick={broadcastStore.runBroadcast}
          disabled={!submitEnabled}
        >
          <Send size={14} />
          {broadcastBusy
            ? at("btn_sending", {}, "Sending...")
            : at("btn_queue", {}, "Queue Message")}
        </AdminButton>
        {#if broadcastResult}
          <span class="admin-muted"
            >{at("broadcast_stat_queued", {}, "Queued")}: {broadcastResult.queued} · {at(
              "broadcast_stat_failed",
              {},
              "Failed"
            )}: {broadcastResult.failed}{#if broadcastResult.channels.includes("email")}
              · {at("broadcast_stat_email_queued", {}, "Email queued")}: {broadcastResult.emailQueued}{/if}</span
          >
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .broadcast-channels {
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
  }

  .broadcast-channel {
    display: inline-flex;
    gap: 8px;
    align-items: center;
    cursor: pointer;
  }

  .broadcast-preview-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .broadcast-preview-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .broadcast-preview {
    padding: 12px 14px;
    border: 1px solid var(--admin-border, #2a2f3a);
    border-radius: 10px;
    background: var(--admin-surface-2, #10141b);
    font-size: 14px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .broadcast-preview-empty {
    color: var(--admin-text-dim, #5d6573);
  }

  .broadcast-preview :global(p) {
    margin: 0 0 8px 0;
  }

  .broadcast-preview :global(p:last-child) {
    margin-bottom: 0;
  }

  .broadcast-preview :global(pre) {
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--admin-surface, #0b0e14);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px;
  }

  .broadcast-preview :global(blockquote) {
    margin: 0 0 8px 0;
    padding-left: 10px;
    border-left: 3px solid var(--admin-border, #2a2f3a);
    color: var(--admin-text-muted, #9aa3b2);
  }

  .broadcast-preview :global(.broadcast-preview-chip) {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--admin-accent, #00fe7a) 18%, transparent);
    color: var(--admin-accent, #00fe7a);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
  }

  .broadcast-preview-warn {
    color: #f4b740;
  }
</style>

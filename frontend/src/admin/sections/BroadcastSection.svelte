<script lang="ts">
  import { getBroadcastStore, getTranslationsStore } from "$lib/admin/context";
  import { Checkbox, ImageAttachment, Input } from "$components/ui/index.js";
  import { Send } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import MessageButtonsEditor from "$lib/admin/components/MessageButtonsEditor.svelte";
  import MessageComposer from "$lib/admin/components/MessageComposer.svelte";
  import MessageLocaleTabs from "$lib/admin/components/MessageLocaleTabs.svelte";
  import { previewHtmlFromWire } from "$lib/richtext/telegramHtml";
  import BroadcastHistory from "./BroadcastHistory.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at, currentLang = "en" }: { at: TranslateFn; currentLang?: string } = $props();
  const broadcastStore = getBroadcastStore();
  const translationsStore = getTranslationsStore();

  // The tab set is whatever the deployment has, so adding a language on the
  // translations screen adds a tab here without touching this file. The
  // request fires once and its guard is deliberately non-reactive: reading the
  // store's own state here would re-run on every mutation the load causes.
  let languagesRequested = false;
  $effect(() => {
    if (languagesRequested) return;
    languagesRequested = true;
    void translationsStore.loadTranslations();
  });
  const languages = $derived(translationsStore.translationLanguages ?? []);
  const activeLanguage = $derived(broadcastStore.broadcastLanguage || languages[0]?.code || "");
  const localizedTexts = $derived(broadcastStore.broadcastTexts ?? {});
  const activeText = $derived(
    activeLanguage ? (localizedTexts[activeLanguage] ?? "") : broadcastStore.broadcastText
  );
  const writtenLanguages = $derived(
    Object.entries(localizedTexts)
      .filter(([, value]) => String(value ?? "").trim())
      .map(([code]) => code)
  );

  function setText(next: string): void {
    if (!activeLanguage) {
      broadcastStore.updateField({ broadcastText: next });
      return;
    }
    broadcastStore.updateField({
      broadcastTexts: { ...localizedTexts, [activeLanguage]: next },
    });
  }

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
    activeText.trim() ? previewHtmlFromWire(activeText, PREVIEW_SAMPLES) : ""
  );

  const broadcastTarget = $derived(broadcastStore.broadcastTarget);
  const broadcastTargetError = $derived(broadcastStore.broadcastTargetError);
  const broadcastBusy = $derived(broadcastStore.broadcastBusy);
  const broadcastResult = $derived(broadcastStore.broadcastResult);
  const broadcastCounts = $derived(broadcastStore.broadcastCounts as Record<string, number> | null);
  const broadcastCountsLoading = $derived(Boolean(broadcastStore.broadcastCountsLoading));
  const telegramEnabled = $derived(broadcastStore.broadcastTelegramEnabled);
  const excludeBlockedTelegram = $derived(broadcastStore.broadcastExcludeBlockedTelegram);
  const emailEnabled = $derived(broadcastStore.broadcastEmailEnabled);
  const emailAvailable = $derived(broadcastStore.broadcastEmailAvailable);
  const emailAvailabilityKnown = $derived(broadcastStore.broadcastEmailAvailabilityKnown);
  const emailSelectable = $derived(!emailAvailabilityKnown || emailAvailable);
  const emailSubject = $derived(broadcastStore.broadcastEmailSubject);
  const broadcastButtons = $derived(broadcastStore.broadcastButtons);
  const promoOptions = $derived(broadcastStore.broadcastPromoOptions);
  const promoOptionsLoading = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoading));
  const promoOptionsLoaded = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoaded));
  let scheduleNow = $state(Date.now());
  const scheduleEnabled = $derived(Boolean(broadcastStore.broadcastScheduleEnabled));
  const scheduledAt = $derived(broadcastStore.broadcastScheduledAt);
  const minimumScheduledAt = $derived(datetimeLocalValue(nextMinute(scheduleNow)));
  const scheduleInvalid = $derived.by(() => {
    if (!scheduleEnabled) return false;
    const date = new Date(scheduledAt);
    return !scheduledAt || Number.isNaN(date.getTime()) || date.getTime() <= scheduleNow;
  });
  const submitEnabled = $derived(!scheduleInvalid && broadcastStore.canSubmit());
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

  function datetimeLocalValue(timestamp: number): string {
    const date = new Date(timestamp);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }

  function nextMinute(timestamp: number): number {
    return Math.ceil((timestamp + 1) / 60_000) * 60_000;
  }

  function defaultScheduledAt(timestamp: number): string {
    return datetimeLocalValue(timestamp + 60 * 60 * 1000);
  }

  function toggleSchedule(checked: boolean): void {
    const now = Date.now();
    scheduleNow = now;
    const existing = new Date(scheduledAt);
    const validExisting =
      scheduledAt && !Number.isNaN(existing.getTime()) && existing.getTime() > now;
    broadcastStore.updateField({
      broadcastScheduleEnabled: checked,
      broadcastScheduledAt: checked
        ? validExisting
          ? scheduledAt
          : defaultScheduledAt(now)
        : scheduledAt,
    });
  }

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
    const scheduleTimer = window.setInterval(() => {
      scheduleNow = Date.now();
    }, 15_000);
    const requestedTarget = routeTarget();
    if (requestedTarget) {
      // Set before discovery completes so a plugin audience is retained when
      // the counts response supplies the dynamic target catalog.
      broadcastStore.updateField({ broadcastTarget: requestedTarget, broadcastTargetError: null });
    }
    void broadcastStore.loadCounts().then(() => {
      if (!requestedTarget) return;
      const available = broadcastStore.BROADCAST_TARGET_OPTIONS.some(
        (option) => option.value === requestedTarget && !option.disabled
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
    return () => window.clearInterval(scheduleTimer);
  });
</script>

<div class="admin-card">
  <header class="admin-card-head">
    <h3>{at("broadcast_title", {}, "Broadcast")}</h3>
    <small>{at("broadcast_subtitle", {}, "Delivery via message queue")}</small>
  </header>
  <div class="admin-card-body">
    <div class="admin-form">
      <div class="broadcast-setup-grid">
        <div class="admin-field-label broadcast-control-panel broadcast-audience-control">
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
        </div>
        <div class="admin-field-label broadcast-control-panel">
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
          {#if telegramEnabled}
            <label class="broadcast-channel broadcast-blocked-filter">
              <Checkbox
                checked={excludeBlockedTelegram}
                ariaLabel={at(
                  "broadcast_exclude_blocked_telegram",
                  {},
                  "Skip users who blocked the bot"
                )}
                onCheckedChange={(checked) =>
                  broadcastStore.updateField({ broadcastExcludeBlockedTelegram: checked })}
              />
              <span
                >{at(
                  "broadcast_exclude_blocked_telegram",
                  {},
                  "Skip users who blocked the bot"
                )}</span
              >
            </label>
            <small class="admin-muted"
              >{at(
                "broadcast_exclude_blocked_telegram_hint",
                {},
                "Only Telegram delivery is skipped; email delivery is unchanged"
              )}</small
            >
          {/if}
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
        <div class="admin-field-label broadcast-control-panel broadcast-language-control">
          <span>{at("broadcast_language_label", {}, "Language")}</span>
          <MessageLocaleTabs
            {languages}
            active={activeLanguage}
            written={writtenLanguages}
            {at}
            onSelect={(code) => broadcastStore.updateField({ broadcastLanguage: code })}
          />
        </div>
        <div
          class="admin-field-label broadcast-control-panel broadcast-schedule-control"
          class:is-invalid={scheduleInvalid}
        >
          <span>{at("broadcast_schedule_label", {}, "Send time")}</span>
          <div class="broadcast-schedule-row">
            <label class="broadcast-channel broadcast-schedule-toggle">
              <Checkbox
                checked={scheduleEnabled}
                ariaLabel={at("broadcast_schedule_later", {}, "Schedule for later")}
                onCheckedChange={toggleSchedule}
              />
              {#if !scheduleEnabled}
                <span>{at("broadcast_schedule_later", {}, "Schedule for later")}</span>
              {/if}
            </label>
            {#if scheduleEnabled}
              <div class="broadcast-schedule-input">
                <Input
                  id="broadcast-scheduled-at"
                  class={scheduleInvalid ? "input-error" : ""}
                  type="datetime-local"
                  value={scheduledAt}
                  min={minimumScheduledAt}
                  aria-label={at("broadcast_scheduled_at", {}, "Scheduled")}
                  aria-invalid={scheduleInvalid}
                  aria-describedby={scheduleInvalid ? "broadcast-schedule-error" : undefined}
                  oninput={(event) =>
                    broadcastStore.updateField({
                      broadcastScheduledAt: (event.currentTarget as HTMLInputElement).value,
                    })}
                />
              </div>
            {/if}
          </div>
          {#if scheduleEnabled && scheduleInvalid}
            <small
              id="broadcast-schedule-error"
              class="admin-field-error broadcast-schedule-error"
              role="alert"
            >
              {at("broadcast_schedule_future", {}, "The send time must be in the future")}
            </small>
          {/if}
        </div>
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
        <MessageComposer
          value={activeText}
          onInput={setText}
          shortcodes={broadcastStore.broadcastShortcodes}
          onRequestShortcodes={broadcastStore.loadShortcodes}
          {at}
          placeholder={at("broadcast_editor_placeholder", {}, "Broadcast text...")}
        />
      </div>

      <div class="admin-field-label">
        <span>{at("message_image_label", {}, "Image")}</span>
        <ImageAttachment
          bind:file={broadcastStore.broadcastImage}
          disabled={broadcastBusy}
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

      <div class="admin-field-label">
        <div class="broadcast-preview-head">
          <span>{at("broadcast_preview_title", {}, "Preview")}</span>
          <div class="broadcast-preview-actions">
            <AdminButton
              size="sm"
              variant="ghost"
              disabled={previewBusy || (!activeText.trim() && !broadcastStore.broadcastImage)}
              onclick={() => broadcastStore.sendPreview("render")}
            >
              {at("broadcast_preview_render", {}, "Refresh with data")}
            </AdminButton>
            <AdminButton
              size="sm"
              variant="ghost"
              disabled={previewBusy || (!activeText.trim() && !broadcastStore.broadcastImage)}
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
        <MessageButtonsEditor
          language={activeLanguage}
          buttons={broadcastButtons}
          {at}
          max={broadcastStore.MAX_BROADCAST_BUTTONS}
          {promoOptions}
          {promoOptionsLoading}
          {promoOptionsLoaded}
          onAdd={broadcastStore.addButton}
          onRemove={broadcastStore.removeButton}
          onUpdate={broadcastStore.updateButton}
          onReorder={broadcastStore.moveButton}
          onRequestPromoOptions={broadcastStore.loadPromoOptions}
        />
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
            : scheduleEnabled
              ? at("broadcast_schedule_action", {}, "Schedule broadcast")
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

<BroadcastHistory {at} {currentLang} />

<style>
  .broadcast-setup-grid {
    display: grid;
    grid-template-columns: minmax(230px, 1.3fr) minmax(180px, 0.75fr) minmax(210px, 0.95fr) minmax(
        260px,
        1.15fr
      );
    gap: 10px;
    align-items: stretch;
  }

  .broadcast-control-panel {
    min-width: 0;
    padding: 10px 11px;
    border: 1px solid color-mix(in srgb, var(--admin-border) 82%, transparent);
    border-radius: 11px;
    background: var(--admin-surface-2);
    transition:
      border-color 0.16s ease,
      background 0.16s ease;
  }

  .broadcast-control-panel > span:first-child {
    color: var(--admin-text-muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }

  .broadcast-language-control :global(.message-locale-tabs) {
    min-height: 36px;
    align-items: center;
    margin: 0;
  }

  .broadcast-channels {
    display: flex;
    gap: 16px;
    align-items: center;
    min-height: 36px;
    flex-wrap: wrap;
  }

  .broadcast-channel {
    display: inline-flex;
    gap: 8px;
    align-items: center;
    cursor: pointer;
  }

  .broadcast-blocked-filter {
    margin-top: 3px;
    font-size: 12px;
  }

  .broadcast-schedule-row {
    display: flex;
    gap: 8px;
    align-items: center;
    min-width: 0;
    min-height: 36px;
  }

  .broadcast-schedule-toggle {
    flex: 0 0 auto;
  }

  .broadcast-schedule-input {
    display: flex;
    min-width: 0;
    flex: 1 1 auto;
    animation: broadcast-schedule-input-in 0.16s ease-out both;
  }

  .broadcast-schedule-input :global(input[type="datetime-local"]) {
    width: auto;
    height: 36px;
    min-width: 0;
    min-height: 36px;
    flex: 1 1 0;
  }

  .broadcast-schedule-input :global(.input-error) {
    background: color-mix(in srgb, var(--danger) 8%, var(--admin-bg));
  }

  .broadcast-schedule-control.is-invalid {
    border-color: color-mix(in srgb, var(--danger) 68%, var(--admin-border));
    background: color-mix(in srgb, var(--danger) 5%, var(--admin-surface-2));
  }

  .broadcast-schedule-error {
    line-height: 1.35;
  }

  @keyframes broadcast-schedule-input-in {
    from {
      opacity: 0;
      transform: translateX(4px);
    }
    to {
      opacity: 1;
      transform: none;
    }
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
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    color: var(--accent);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
  }

  .broadcast-preview-warn {
    color: #f4b740;
  }

  @media (max-width: 1180px) {
    .broadcast-setup-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 680px) {
    .broadcast-setup-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .broadcast-control-panel {
      padding: 10px;
    }

    .broadcast-channels {
      gap: 12px;
      min-height: 46px;
    }

    .broadcast-audience-control :global(.admin-select-trigger),
    .broadcast-language-control :global(.message-locale-tabs),
    .broadcast-schedule-row {
      min-height: 46px;
    }

    .broadcast-audience-control :global(.admin-select-trigger) {
      height: 46px;
    }

    .broadcast-schedule-input :global(input[type="datetime-local"]) {
      height: 46px;
      min-height: 46px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .broadcast-control-panel {
      transition: none;
    }

    .broadcast-schedule-input {
      animation: none;
    }
  }
</style>

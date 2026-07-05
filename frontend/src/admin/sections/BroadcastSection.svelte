<script lang="ts">
  import { getBroadcastStore } from "$lib/admin/context";
  import { Checkbox, Input, Sortable, Textarea } from "$components/ui/index.js";
  import { Plus, Send, Trash2 } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import type {
    BroadcastButtonDraft,
    BroadcastButtonKind,
  } from "$lib/admin/stores/broadcastStore.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at }: { at: TranslateFn } = $props();
  const broadcastStore = getBroadcastStore();

  const broadcastTarget = $derived(broadcastStore.broadcastTarget);
  const broadcastText = $derived(broadcastStore.broadcastText);
  const broadcastBusy = $derived(broadcastStore.broadcastBusy);
  const broadcastResult = $derived(broadcastStore.broadcastResult);
  const broadcastCounts = $derived(broadcastStore.broadcastCounts as Record<string, number> | null);
  const broadcastCountsLoading = $derived(Boolean(broadcastStore.broadcastCountsLoading));
  const telegramEnabled = $derived(broadcastStore.broadcastTelegramEnabled);
  const emailEnabled = $derived(broadcastStore.broadcastEmailEnabled);
  const emailAvailable = $derived(broadcastStore.broadcastEmailAvailable);
  const emailSubject = $derived(broadcastStore.broadcastEmailSubject);
  const broadcastButtons = $derived(broadcastStore.broadcastButtons);
  const promoOptions = $derived(broadcastStore.broadcastPromoOptions);
  const promoOptionsLoading = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoading));
  const promoOptionsLoaded = $derived(Boolean(broadcastStore.broadcastPromoOptionsLoaded));
  const hasPromoButtons = $derived(broadcastButtons.some((button) => button.kind !== "url"));
  const submitEnabled = $derived(broadcastStore.canSubmit());
  const handleTargetChange = (value: string) => {
    broadcastStore.updateField({ broadcastTarget: value });
  };

  const BROADCAST_TARGET_OPTIONS = broadcastStore.BROADCAST_TARGET_OPTIONS;

  const buttonKindOptions = $derived([
    { value: "url", label: at("broadcast_button_kind_url", {}, "Ссылка") },
    {
      value: "promo_bot",
      label: at("broadcast_button_kind_promo_bot", {}, "Промокод — в боте"),
    },
    {
      value: "promo_webapp",
      label: at("broadcast_button_kind_promo_webapp", {}, "Промокод — в веб-аппе"),
    },
  ]);

  // Append the resolved audience size to each option once counts are loaded.
  const targetOptions = $derived(
    BROADCAST_TARGET_OPTIONS.map((option) => {
      const count = broadcastCounts?.[option.value];
      if (count != null) return { ...option, label: `${option.label} (${count})` };
      if (broadcastCountsLoading) return { ...option, label: `${option.label} (...)` };
      return option;
    })
  );

  onMount(() => {
    broadcastStore.loadCounts();
    if (broadcastStore.broadcastButtons.some((button) => button.kind !== "url")) {
      broadcastStore.loadPromoOptions();
    }
  });
</script>

<div class="admin-card">
  <header class="admin-card-head">
    <h3>{at("broadcast_title", {}, "Рассылка")}</h3>
    <small>{at("broadcast_subtitle", {}, "Доставка через очередь сообщений")}</small>
  </header>
  <div class="admin-card-body">
    <div class="admin-form">
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_audience", {}, "Аудитория")}</span>
        <AdminSelect
          value={broadcastTarget}
          items={targetOptions}
          ariaLabel={at("broadcast_label_audience", {}, "Аудитория")}
          onValueChange={handleTargetChange}
        />
      </Label.Root>
      <div class="admin-field-label">
        <span>{at("broadcast_channels_label", {}, "Каналы доставки")}</span>
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
              checked={emailEnabled && emailAvailable}
              disabled={!emailAvailable}
              ariaLabel={at("broadcast_channel_email", {}, "Email")}
              onCheckedChange={(checked) =>
                broadcastStore.updateField({ broadcastEmailEnabled: checked })}
            />
            <span>{at("broadcast_channel_email", {}, "Email")}</span>
          </label>
        </div>
        {#if !emailAvailable}
          <small class="admin-muted"
            >{at(
              "broadcast_email_unavailable_hint",
              {},
              "Email-канал недоступен: SMTP не настроен"
            )}</small
          >
        {/if}
      </div>
      {#if emailEnabled && emailAvailable}
        <Label.Root class="admin-field-label">
          <span>{at("broadcast_email_subject_label", {}, "Тема письма")}</span>
          <Input
            value={emailSubject}
            placeholder={at(
              "broadcast_email_subject_placeholder",
              {},
              "Пусто — будет использована тема по умолчанию"
            )}
            oninput={(e) =>
              broadcastStore.updateField({
                broadcastEmailSubject: (e.currentTarget as HTMLInputElement).value,
              })}
          />
        </Label.Root>
      {/if}
      <Label.Root class="admin-field-label">
        <span>{at("broadcast_label_text", {}, "Текст сообщения")}</span>
        <small>{at("broadcast_hint_text", {}, "Поддерживается HTML-разметка Telegram")}</small>
        <Textarea
          class="admin-textarea"
          rows={6}
          value={broadcastText}
          oninput={(e) =>
            broadcastStore.updateField({
              broadcastText: (e.currentTarget as HTMLTextAreaElement).value,
            })}
        />
      </Label.Root>
      <div class="admin-field-label">
        <span>{at("broadcast_buttons_label", {}, "Кнопки")}</span>
        <small class="admin-muted"
          >{at(
            "broadcast_buttons_hint",
            {},
            "До 4 кнопок: в Telegram — инлайн-кнопки, в email — кнопки-ссылки. Промокод активируется в один клик."
          )}</small
        >
        <div class="admin-row-editor">
          <Sortable
            items={broadcastButtons}
            class="admin-row-editor-line admin-row-editor-broadcast"
            getKey={(button: BroadcastButtonDraft) => button.id}
            handleLabel={at("broadcast_button_reorder", {}, "Перетащите, чтобы изменить порядок")}
            onReorder={broadcastStore.moveButton}
          >
            {#snippet children(button: BroadcastButtonDraft, index: number)}
              <AdminSelect
                value={button.kind}
                items={buttonKindOptions}
                ariaLabel={at("broadcast_buttons_label", {}, "Кнопки")}
                onValueChange={(value) =>
                  broadcastStore.updateButton(index, { kind: value as BroadcastButtonKind })}
              />
              <Input
                class="input"
                value={button.label}
                maxlength={64}
                placeholder={at("broadcast_button_label_placeholder", {}, "Текст кнопки")}
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
                    ? at("broadcast_button_promo_loading", {}, "Загрузка промокодов...")
                    : at("broadcast_button_promo_select", {}, "Выберите промокод")}
                  ariaLabel={at("broadcast_button_promo_select", {}, "Выберите промокод")}
                  onValueChange={(value) =>
                    broadcastStore.updateButton(index, { promoCode: value })}
                />
              {/if}
              <AdminButton
                size="sm"
                variant="danger"
                aria-label={at("broadcast_button_remove", {}, "Удалить кнопку")}
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
              "Нет активных промокодов — создайте код в разделе «Промокоды»"
            )}</small
          >
        {/if}
        {#if broadcastButtons.length < broadcastStore.MAX_BROADCAST_BUTTONS}
          <div>
            <AdminButton variant="ghost" onclick={broadcastStore.addButton}>
              <Plus size={14} />
              {at("broadcast_button_add", {}, "Добавить кнопку")}
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
            ? at("btn_sending", {}, "Отправка...")
            : at("btn_queue", {}, "Поставить в очередь")}
        </AdminButton>
        {#if broadcastResult}
          <span class="admin-muted"
            >{at("broadcast_stat_queued", {}, "В очереди")}: {broadcastResult.queued} · {at(
              "broadcast_stat_failed",
              {},
              "Неудач"
            )}: {broadcastResult.failed}{#if broadcastResult.channels.includes("email")}
              · {at("broadcast_stat_email_queued", {}, "Email в очереди")}: {broadcastResult.emailQueued}{/if}</span
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
</style>

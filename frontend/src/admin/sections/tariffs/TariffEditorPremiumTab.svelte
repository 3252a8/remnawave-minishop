<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Tabs, Label } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Plus, Trash2, X } from "$components/ui/icons.js";
  import { normalizeUuidList } from "$lib/admin/tariffDraft.js";
  import type { PanelSquad, TariffDraft, TariffsCatalog } from "$lib/admin/stores/tariffsStore";
  import {
    addDraftSquad,
    currencyPriceAriaLabel as formatCurrencyPriceAriaLabel,
    currencyPriceColumnLabel as formatCurrencyPriceColumnLabel,
    defaultCurrencyCode as getDefaultCurrencyCode,
    draftInputHandler,
    draftRowInputHandler,
    draftRowKey,
    moveDraftRowHandler,
    panelSquadOptions as toPanelSquadOptions,
    type DraftRow,
    type ReorderHandler,
    type SelectOption,
    type TranslateFn,
  } from "./tariffEditorTabUtils.js";

  let { at }: { at: TranslateFn } = $props();

  const tariffsStore = getTariffsStore();
  const tariffsState = $derived(tariffsStore);
  const tariffDraft: TariffDraft = $derived(tariffsState.tariffDraft);
  const panelSquads: PanelSquad[] = $derived(tariffsState.panelSquads || []);
  const tariffsCatalog: TariffsCatalog = $derived(tariffsState.tariffsCatalog);
  const panelSquadOptions: SelectOption[] = $derived(toPanelSquadOptions(panelSquads));
  const defaultCurrencyCode = $derived(getDefaultCurrencyCode(tariffsCatalog));
  const currencyPriceColumnLabel = $derived(
    formatCurrencyPriceColumnLabel(at, defaultCurrencyCode)
  );
  const currencyPriceAriaLabel = $derived(formatCurrencyPriceAriaLabel(at, defaultCurrencyCode));
  const movePremiumTopupRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "premiumTopupRows");

  function addPremiumSquad(value: string): void {
    addDraftSquad(tariffsStore, "premiumSquadUuids", value);
  }

  function addPremiumTopupRow(): void {
    tariffsStore.addDraftRow("premiumTopupRows", { gb: 10, price: "", stars: "" });
  }
</script>

<Tabs.Content value="premium" class="admin-tabs-content">
  <section class="admin-editor-section">
    <header class="admin-editor-section-head">
      <div class="admin-editor-section-title">
        <strong
          >{at("tariff_premium_head", {}, "Premium-доступ и отдельный счётчик трафика")}</strong
        >
        <small
          >{at(
            "tariff_premium_subhead",
            {},
            "Premium-сквады дают пользователю доступ к более быстрым/премиальным нодам; их трафик считается отдельно от основного, чтобы можно было ограничить или продавать дополнительно"
          )}</small
        >
      </div>
    </header>
    <div class="admin-form-row admin-form-row-2">
      <Label.Root class="admin-field-label">
        <span>{at("tariff_label_premium_name_ru", {}, "Название premium-раздела, RU")}</span>
        <small
          >{at(
            "tariff_hint_premium_name_ru",
            {},
            "Эта строка заменит «Premium-серверы» в кабинете, докупках и карточках лимитов."
          )}</small
        >
        <Input
          class="input"
          type="text"
          placeholder={at("tariff_placeholder_premium_name_ru", {}, "Premium-серверы")}
          value={tariffDraft.premiumNameRu}
          oninput={draftInputHandler(tariffsStore, "premiumNameRu")}
        />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>{at("tariff_label_premium_name_en", {}, "Название premium-раздела, EN")}</span>
        <small
          >{at("tariff_hint_premium_name_en", {}, "Опционально для английского интерфейса.")}</small
        >
        <Input
          class="input"
          type="text"
          placeholder={at("tariff_placeholder_premium_name_en", {}, "Premium servers")}
          value={tariffDraft.premiumNameEn}
          oninput={draftInputHandler(tariffsStore, "premiumNameEn")}
        />
      </Label.Root>
    </div>
    <div class="admin-form-row admin-form-row-2">
      <div class="admin-field-label">
        <span>{at("tariff_label_premium_squads", {}, "Premium Internal Squads")}</span>
        <small
          >{at(
            "tariff_hint_premium_squads",
            {},
            "Сквады из Remnawave, доступные только владельцам этого тарифа. Трафик считается по их accessible nodes"
          )}</small
        >
        <AdminSelect
          bind:value={tariffsStore.selectedPremiumSquad}
          items={panelSquadOptions}
          placeholder={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
          ariaLabel={at("btn_add_premium_squad", {}, "Добавить premium-сквад")}
          onValueChange={addPremiumSquad}
        />
        <div class="admin-chip-list">
          {#each normalizeUuidList(tariffDraft.premiumSquadUuids) as uuid}
            <button
              type="button"
              class="admin-chip"
              onclick={() => tariffsStore.removeSquadFromDraft("premiumSquadUuids", uuid)}
            >
              {tariffsStore.squadLabel(uuid)}
              <X size={12} />
            </button>
          {/each}
        </div>
      </div>
      <Label.Root class="admin-field-label">
        <span
          >{at(
            "tariff_label_premium_traffic_limit",
            {},
            "Месячный лимит premium-трафика, GB"
          )}</span
        >
        <small
          >{at(
            "tariff_hint_premium_traffic_limit",
            {},
            "Сколько GB через premium-сквады включено в тариф каждый месяц. 0 или пусто — отдельного premium-лимита нет (premium-нодами можно пользоваться без ограничения)"
          )}</small
        >
        <Input
          class="input"
          type="number"
          min="0"
          step="0.1"
          placeholder="50"
          value={tariffDraft.premium_monthly_gb}
          oninput={draftInputHandler(tariffsStore, "premium_monthly_gb")}
        />
      </Label.Root>
    </div>
  </section>

  <section class="admin-editor-section">
    <header class="admin-editor-section-head">
      <div class="admin-editor-section-title">
        <strong>{at("tariff_premium_topup_title", {}, "Докупка premium-трафика")}</strong>
        <small
          >{at(
            "tariff_premium_topup_subtitle",
            {},
            "Пакеты для расширения месячного premium-лимита, когда пользователь его исчерпал"
          )}</small
        >
      </div>
      <div class="admin-editor-section-actions">
        <AdminButton size="sm" onclick={addPremiumTopupRow}
          ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
        >
      </div>
    </header>
    {#if tariffDraft.premiumTopupRows.length}
      <div class="admin-row-editor">
        <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
          <span></span>
          <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
          <span>{currencyPriceColumnLabel}</span>
          <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
          <span></span>
        </div>
        <Sortable
          items={tariffDraft.premiumTopupRows}
          class="admin-row-editor-line admin-row-editor-drag"
          getKey={draftRowKey}
          handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
          onReorder={movePremiumTopupRow}
        >
          {#snippet children(row: DraftRow, index: number)}
            <Input
              class="input"
              type="number"
              min="0.1"
              step="0.1"
              placeholder="10"
              value={row.gb}
              oninput={draftRowInputHandler(tariffsStore, "premiumTopupRows", index, "gb")}
              aria-label={at("tariff_col_volume_gb", {}, "Объём premium-пакета в GB")}
            />
            <Input
              class="input"
              type="number"
              min="0"
              step="0.01"
              placeholder="199"
              value={row.price}
              oninput={draftRowInputHandler(tariffsStore, "premiumTopupRows", index, "price")}
              aria-label={currencyPriceAriaLabel}
            />
            <Input
              class="input"
              type="number"
              min="0"
              step="1"
              placeholder="100"
              value={row.stars}
              oninput={draftRowInputHandler(tariffsStore, "premiumTopupRows", index, "stars")}
              aria-label={at(
                "tariff_label_price_stars",
                {},
                "Цена premium-пакета в Telegram Stars"
              )}
            />
            <AdminButton
              size="sm"
              variant="danger"
              onclick={() => tariffsStore.removeDraftRow("premiumTopupRows", index)}
              aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
            >
          {/snippet}
        </Sortable>
      </div>
    {/if}
  </section>
</Tabs.Content>

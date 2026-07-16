<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Tabs, Label, Switch } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Plus, Trash2, X } from "$components/ui/icons.js";
  import { normalizeUuidList } from "$lib/admin/tariffDraft";
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
          >{at("tariff_premium_head", {}, "Premium access and a separate traffic counter")}</strong
        >
        <small
          >{at(
            "tariff_premium_subhead",
            {},
            "Premium squads give the user access to faster/premium nodes; their traffic is counted separately from main traffic so it can be limited or sold separately"
          )}</small
        >
      </div>
    </header>
    <div class="admin-form-row admin-form-row-2">
      <Label.Root class="admin-field-label">
        <span>{at("tariff_label_premium_name_ru", {}, "Premium section name, RU")}</span>
        <small
          >{at(
            "tariff_hint_premium_name_ru",
            {},
            'This text replaces "Premium servers" in the account, top-ups, and limit cards.'
          )}</small
        >
        <Input
          class="input"
          type="text"
          placeholder={at("tariff_placeholder_premium_name_ru", {}, "Premium servers")}
          value={tariffDraft.premiumNameRu}
          oninput={draftInputHandler(tariffsStore, "premiumNameRu")}
        />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>{at("tariff_label_premium_name_en", {}, "Premium section name, EN")}</span>
        <small>{at("tariff_hint_premium_name_en", {}, "Optional for the English interface.")}</small
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
            "Remnawave squads available only to owners of this tariff. Traffic is counted by their accessible nodes"
          )}</small
        >
        <AdminSelect
          bind:value={tariffsStore.selectedPremiumSquad}
          items={panelSquadOptions}
          placeholder={at("btn_add_premium_squad", {}, "Add premium squad")}
          ariaLabel={at("btn_add_premium_squad", {}, "Add premium squad")}
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
          >{at("tariff_label_premium_traffic_limit", {}, "Monthly premium traffic limit, GB")}</span
        >
        <small
          >{at(
            "tariff_hint_premium_traffic_limit",
            {},
            "How many GB through premium squads are included each month. 0 or empty means there is no separate premium limit"
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
        <strong>{at("tariff_premium_topup_title", {}, "Premium traffic top-up")}</strong>
        <small
          >{at(
            "tariff_premium_topup_subtitle",
            {},
            "Packages that extend the monthly premium limit when the user runs out"
          )}</small
        >
      </div>
      <div class="admin-editor-section-actions">
        <AdminButton size="sm" onclick={addPremiumTopupRow}
          ><Plus size={12} /> {at("tariff_btn_package", {}, "Package")}</AdminButton
        >
      </div>
    </header>
    <div class="admin-action-row admin-action-row-bordered">
      <Switch.Root
        aria-labelledby="tariff-premium-topup-always-toggle-label"
        checked={Boolean(tariffDraft.premium_topup_always_available)}
        onCheckedChange={(value) =>
          tariffsStore.updateDraftField("premium_topup_always_available", value)}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <Label.Root id="tariff-premium-topup-always-toggle-label" class="admin-action-label">
        <strong>{at("tariff_premium_topup_always_label", {}, "Top-up always available")}</strong>
        <small
          >{at(
            "tariff_premium_topup_always_hint",
            {},
            "By default, premium traffic top-up appears to the user (in the mini app and bot menu) after at least 80% of the premium limit is used. Enable this to show the offer regardless of usage percentage."
          )}</small
        >
      </Label.Root>
    </div>
    {#if tariffDraft.premiumTopupRows.length}
      <div class="admin-row-editor">
        <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
          <span></span>
          <span>{at("tariff_col_volume_gb", {}, "Volume, GB")}</span>
          <span>{currencyPriceColumnLabel}</span>
          <span>{at("tariff_col_price_stars_full", {}, "Price, ⭐ Stars")}</span>
          <span></span>
        </div>
        <Sortable
          items={tariffDraft.premiumTopupRows}
          class="admin-row-editor-line admin-row-editor-drag"
          getKey={draftRowKey}
          handleLabel={at("tariff_package_reorder", {}, "Drag to reorder")}
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
              aria-label={at("tariff_col_volume_gb", {}, "Volume, GB")}
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
              aria-label={at("tariff_label_price_stars", {}, "Price in Telegram Stars")}
            />
            <AdminButton
              size="sm"
              variant="danger"
              onclick={() => tariffsStore.removeDraftRow("premiumTopupRows", index)}
              aria-label={at("btn_delete", {}, "Delete")}><Trash2 size={13} /></AdminButton
            >
          {/snippet}
        </Sortable>
      </div>
    {/if}
  </section>
</Tabs.Content>

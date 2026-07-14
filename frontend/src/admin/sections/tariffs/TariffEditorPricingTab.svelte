<script lang="ts">
  import { getTariffsStore } from "$lib/admin/context";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Plus, Trash2 } from "$components/ui/icons.js";
  import type { TariffDraft, TariffsCatalog } from "$lib/admin/stores/tariffsStore";
  import {
    currencyPriceAriaLabel as formatCurrencyPriceAriaLabel,
    currencyPriceColumnLabel as formatCurrencyPriceColumnLabel,
    defaultCurrencyCode as getDefaultCurrencyCode,
    draftRowInputHandler,
    draftRowKey,
    moveDraftRowHandler,
    type DraftRow,
    type ReorderHandler,
    type TranslateFn,
  } from "./tariffEditorTabUtils.js";

  let { at }: { at: TranslateFn } = $props();

  const tariffsStore = getTariffsStore();
  const tariffsState = $derived(tariffsStore);
  const tariffDraft: TariffDraft = $derived(tariffsState.tariffDraft);
  const tariffsCatalog: TariffsCatalog = $derived(tariffsState.tariffsCatalog);
  const defaultCurrencyCode = $derived(getDefaultCurrencyCode(tariffsCatalog));
  const currencyPriceColumnLabel = $derived(
    formatCurrencyPriceColumnLabel(at, defaultCurrencyCode)
  );
  const currencyPriceAriaLabel = $derived(formatCurrencyPriceAriaLabel(at, defaultCurrencyCode));
  const movePeriodRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "periodRows");
  const moveTrafficRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "trafficRows");

  function addPeriodRow(): void {
    tariffsStore.addDraftRow("periodRows", {
      months: 1,
      rub: "",
      stars: "",
      referral_inviter: "",
      referral_referee: "",
    });
  }

  function addTrafficRow(): void {
    tariffsStore.addDraftRow("trafficRows", { gb: 10, price: "", stars: "" });
  }
</script>

<Tabs.Content value="pricing" class="admin-tabs-content">
  {#if tariffDraft.billing_model === "period"}
    <section class="admin-editor-section">
      <header class="admin-editor-section-head">
        <div class="admin-editor-section-title">
          <strong>{at("tariff_pricing_period_title", {}, "Subscription periods and prices")}</strong
          >
          <small
            >{at(
              "tariff_pricing_period_subtitle",
              {},
              "Each row is a separate storefront option: how many months the user pays for and how much it costs. Drag rows by the handle to set the period order in the bot and the web app"
            )}</small
          >
        </div>
        <AdminButton size="sm" onclick={addPeriodRow}>
          <Plus size={13} />
          {at("tariff_btn_period", {}, "Period")}
        </AdminButton>
      </header>
      {#if !tariffDraft.periodRows.length}
        <p class="admin-muted">
          {at(
            "tariff_pricing_empty",
            {},
            "Add at least one period so the tariff appears in the storefront."
          )}
        </p>
      {:else}
        <div class="admin-row-editor">
          <div class="admin-row-editor-line admin-row-editor-period admin-row-editor-header">
            <span></span>
            <span>{at("tariff_col_period_months", {}, "Period, mo.")}</span>
            <span>{currencyPriceColumnLabel}</span>
            <span>{at("tariff_col_price_stars_full", {}, "Price, ⭐ Stars")}</span>
            <span>{at("tariff_col_ref_inviter", {}, "Inviter bonus")}</span>
            <span>{at("tariff_col_ref_referee", {}, "Friend bonus")}</span>
            <span></span>
          </div>
          <Sortable
            items={tariffDraft.periodRows}
            class="admin-row-editor-line admin-row-editor-period"
            getKey={draftRowKey}
            handleLabel={at("tariff_period_reorder", {}, "Drag to reorder")}
            onReorder={movePeriodRow}
          >
            {#snippet children(row: DraftRow, index: number)}
              <Input
                class="input"
                type="number"
                min="1"
                placeholder="1"
                value={row.months}
                oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "months")}
                aria-label={at("tariff_col_period_months", {}, "Period, mo.")}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="0.01"
                placeholder="299"
                value={row.rub}
                oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "rub")}
                aria-label={currencyPriceAriaLabel}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="150"
                value={row.stars}
                oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "stars")}
                aria-label={at("tariff_label_price_stars", {}, "Price in Telegram Stars")}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="3"
                value={row.referral_inviter}
                oninput={draftRowInputHandler(
                  tariffsStore,
                  "periodRows",
                  index,
                  "referral_inviter"
                )}
                aria-label={at("tariff_label_ref_inviter", {}, "Inviter bonus, days")}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="1"
                value={row.referral_referee}
                oninput={draftRowInputHandler(
                  tariffsStore,
                  "periodRows",
                  index,
                  "referral_referee"
                )}
                aria-label={at("tariff_label_ref_referee", {}, "Friend bonus, days")}
              />
              <AdminButton
                size="sm"
                variant="danger"
                onclick={() => tariffsStore.removeDraftRow("periodRows", index)}
                aria-label={at("btn_delete", {}, "Delete")}
              >
                <Trash2 size={13} />
              </AdminButton>
            {/snippet}
          </Sortable>
        </div>
      {/if}
    </section>
  {:else}
    <section class="admin-editor-section">
      <header class="admin-editor-section-head">
        <div class="admin-editor-section-title">
          <strong>{at("tariff_pricing_traffic_title", {}, "Traffic packages")}</strong>
          <small
            >{at(
              "tariff_pricing_traffic_subtitle",
              {},
              'Base storefront for the traffic model. Each row is an "N gigabytes for N currency units" package. Drag rows by the handle to set the package order in the bot and the web app'
            )}</small
          >
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton size="sm" onclick={addTrafficRow}
            ><Plus size={12} /> {at("tariff_btn_package", {}, "Package")}</AdminButton
          >
        </div>
      </header>
      {#if tariffDraft.trafficRows.length}
        <div class="admin-row-editor">
          <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
            <span></span>
            <span>{at("tariff_col_volume_gb", {}, "Volume, GB")}</span>
            <span>{currencyPriceColumnLabel}</span>
            <span>{at("tariff_col_price_stars_full", {}, "Price, ⭐ Stars")}</span>
            <span></span>
          </div>
          <Sortable
            items={tariffDraft.trafficRows}
            class="admin-row-editor-line admin-row-editor-drag"
            getKey={draftRowKey}
            handleLabel={at("tariff_package_reorder", {}, "Drag to reorder")}
            onReorder={moveTrafficRow}
          >
            {#snippet children(row: DraftRow, index: number)}
              <Input
                class="input"
                type="number"
                min="0.1"
                step="0.1"
                placeholder="50"
                value={row.gb}
                oninput={draftRowInputHandler(tariffsStore, "trafficRows", index, "gb")}
                aria-label={at("tariff_col_volume_gb", {}, "Volume, GB")}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="0.01"
                placeholder="299"
                value={row.price}
                oninput={draftRowInputHandler(tariffsStore, "trafficRows", index, "price")}
                aria-label={currencyPriceAriaLabel}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="150"
                value={row.stars}
                oninput={draftRowInputHandler(tariffsStore, "trafficRows", index, "stars")}
                aria-label={at("tariff_label_price_stars", {}, "Price in Telegram Stars")}
              />
              <AdminButton
                size="sm"
                variant="danger"
                onclick={() => tariffsStore.removeDraftRow("trafficRows", index)}
                aria-label={at("btn_delete", {}, "Delete")}><Trash2 size={13} /></AdminButton
              >
            {/snippet}
          </Sortable>
        </div>
      {/if}
    </section>
  {/if}
</Tabs.Content>

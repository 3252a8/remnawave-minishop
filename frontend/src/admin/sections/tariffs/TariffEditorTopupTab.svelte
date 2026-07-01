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
  const moveTopupRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "topupRows");

  function addTopupRow(): void {
    tariffsStore.addDraftRow("topupRows", { gb: 10, price: "", stars: "" });
  }
</script>

<Tabs.Content value="topup" class="admin-tabs-content">
  {#if tariffDraft.billing_model === "period"}
    <section class="admin-editor-section">
      <header class="admin-editor-section-head">
        <div class="admin-editor-section-title">
          <strong>{at("tariff_topup_title", {}, "Докупка трафика поверх месячного лимита")}</strong>
          <small
            >{at(
              "tariff_topup_subtitle",
              {},
              "Когда у пользователя кончился месячный лимит, ему предложат купить дополнительный пакет, не меняя срок подписки"
            )}</small
          >
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton size="sm" onclick={addTopupRow}
            ><Plus size={12} /> {at("tariff_btn_package", {}, "Пакет")}</AdminButton
          >
        </div>
      </header>
      {#if tariffDraft.topupRows.length}
        <div class="admin-row-editor">
          <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
            <span></span>
            <span>{at("tariff_col_volume_gb", {}, "Объём, GB")}</span>
            <span>{currencyPriceColumnLabel}</span>
            <span>{at("tariff_col_price_stars_full", {}, "Цена, ⭐ Stars")}</span>
            <span></span>
          </div>
          <Sortable
            items={tariffDraft.topupRows}
            class="admin-row-editor-line admin-row-editor-drag"
            getKey={draftRowKey}
            handleLabel={at("tariff_package_reorder", {}, "Перетащите, чтобы изменить порядок")}
            onReorder={moveTopupRow}
          >
            {#snippet children(row: DraftRow, index: number)}
              <Input
                class="input"
                type="number"
                min="0.1"
                step="0.1"
                placeholder="20"
                value={row.gb}
                oninput={draftRowInputHandler(tariffsStore, "topupRows", index, "gb")}
                aria-label={at("tariff_col_volume_gb", {}, "Объём пакета в GB")}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="0.01"
                placeholder="149"
                value={row.price}
                oninput={draftRowInputHandler(tariffsStore, "topupRows", index, "price")}
                aria-label={currencyPriceAriaLabel}
              />
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="75"
                value={row.stars}
                oninput={draftRowInputHandler(tariffsStore, "topupRows", index, "stars")}
                aria-label={at("tariff_label_price_stars", {}, "Цена пакета в Telegram Stars")}
              />
              <AdminButton
                size="sm"
                variant="danger"
                onclick={() => tariffsStore.removeDraftRow("topupRows", index)}
                aria-label={at("btn_delete", {}, "Удалить")}><Trash2 size={13} /></AdminButton
              >
            {/snippet}
          </Sortable>
        </div>
      {/if}
    </section>
  {:else}
    <p class="admin-muted">
      {at(
        "tariff_topup_traffic_hint",
        {},
        "Для трафиковой модели отдельные «докупки» не нужны — пакеты, которые вы настроили на вкладке «Цены», и являются докупками: пользователь покупает их повторно по мере исчерпания."
      )}
    </p>
  {/if}
</Tabs.Content>

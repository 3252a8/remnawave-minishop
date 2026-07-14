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
  const moveHwidRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "hwidRows");

  function addHwidPackageRow(): void {
    tariffsStore.addDraftRow("hwidRows", { count: 1, price: "", stars: "" });
  }
</script>

<Tabs.Content value="hwid" class="admin-tabs-content">
  <section class="admin-editor-section">
    <header class="admin-editor-section-head">
      <div class="admin-editor-section-title">
        <strong>{at("tariff_hwid_packages_title", {}, "Extra device packages (HWID)")}</strong>
        <small
          >{at(
            "tariff_hwid_packages_subtitle",
            {},
            'Extends the limit from the General tab. Each row is a "+N devices for N currency units" package'
          )}</small
        >
      </div>
      <div class="admin-editor-section-actions">
        <AdminButton size="sm" onclick={addHwidPackageRow}
          ><Plus size={12} /> {at("tariff_btn_package", {}, "Package")}</AdminButton
        >
      </div>
    </header>
    {#if tariffDraft.hwidRows.length}
      <div class="admin-row-editor">
        <div class="admin-row-editor-line admin-row-editor-drag admin-row-editor-header">
          <span></span>
          <span>{at("tariff_col_hwid_count", {}, "+ devices")}</span>
          <span>{currencyPriceColumnLabel}</span>
          <span>{at("tariff_col_price_stars_full", {}, "Price, ⭐ Stars")}</span>
          <span></span>
        </div>
        <Sortable
          items={tariffDraft.hwidRows}
          class="admin-row-editor-line admin-row-editor-drag"
          getKey={draftRowKey}
          handleLabel={at("tariff_package_reorder", {}, "Drag to reorder")}
          onReorder={moveHwidRow}
        >
          {#snippet children(row: DraftRow, index: number)}
            <Input
              class="input"
              type="number"
              min="1"
              step="1"
              placeholder="1"
              value={row.count}
              oninput={draftRowInputHandler(tariffsStore, "hwidRows", index, "count")}
              aria-label={at(
                "tariff_label_hwid_count_full",
                {},
                "How many devices does this package add"
              )}
            />
            <Input
              class="input"
              type="number"
              min="0"
              step="0.01"
              placeholder="99"
              value={row.price}
              oninput={draftRowInputHandler(tariffsStore, "hwidRows", index, "price")}
              aria-label={currencyPriceAriaLabel}
            />
            <Input
              class="input"
              type="number"
              min="0"
              step="1"
              placeholder="50"
              value={row.stars}
              oninput={draftRowInputHandler(tariffsStore, "hwidRows", index, "stars")}
              aria-label={at("tariff_label_price_stars", {}, "Price in Telegram Stars")}
            />
            <AdminButton
              size="sm"
              variant="danger"
              onclick={() => tariffsStore.removeDraftRow("hwidRows", index)}
              aria-label={at("btn_delete", {}, "Delete")}><Trash2 size={13} /></AdminButton
            >
          {/snippet}
        </Sortable>
      </div>
    {/if}
  </section>
</Tabs.Content>

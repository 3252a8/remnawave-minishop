<script lang="ts">
  import { adminDurationLabel } from "$lib/admin/tariffPeriods";
  import { getTariffsStore } from "$lib/admin/context";
  import { Input, Sortable } from "$components/ui/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import { AdminButton, AdminSelect } from "$components/patterns/admin/index.js";
  import { Plus, Trash2 } from "$components/ui/icons.js";
  import type { TariffDraft, TariffsCatalog } from "$lib/admin/stores/tariffsStore";
  import {
    applySubscriptionToPeriodRows,
    subscriptionOptionLabel,
    type TributeDraftRow,
    type TributeIssue,
  } from "$lib/admin/tributeCatalog";
  import TributeCatalogButton from "./TributeCatalogButton.svelte";
  import TributeCatalogIssues from "./TributeCatalogIssues.svelte";
  import TributeProductField from "./TributeProductField.svelte";
  import {
    currencyPriceAriaLabel as formatCurrencyPriceAriaLabel,
    currencyPriceColumnLabel as formatCurrencyPriceColumnLabel,
    defaultCurrencyCode as getDefaultCurrencyCode,
    draftRowInputHandler,
    draftRowKey,
    moveDraftRowHandler,
    tributeEnabled as isTributeEnabled,
    tributeSectionVisible as isTributeSectionVisible,
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
  // Tribute mapping is provider configuration, so it stays out of the editor
  // until the provider is switched on — unless this tariff still carries a
  // mapping, which has to stay reachable to be cleared.
  const tributeProviderEnabled = $derived(isTributeEnabled(tariffsState));
  const showTribute = $derived(isTributeSectionVisible(tariffsState, tariffDraft));
  const movePeriodRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "periodRows");
  const moveTrafficRow: ReorderHandler = moveDraftRowHandler(tariffsStore, "trafficRows");

  function addPeriodRow(days = 1): void {
    tariffsStore.addDraftRow("periodRows", {
      duration_days: days,
      rub: "",
      stars: "",
      referral_inviter: "",
      referral_referee: "",
      tribute_period_id: "",
      tribute_link: "",
      tribute_subscription_id: "",
    });
  }

  function addTrafficRow(): void {
    tariffsStore.addDraftRow("trafficRows", {
      gb: 10,
      price: "",
      stars: "",
      tribute_product_id: "",
      tribute_product_link: "",
    });
  }

  // Creator bindings live in Tribute, not here: the catalog lookup fills the
  // identifiers in and reports every divergence the admin must fix in Tribute.
  const tributeCatalog = $derived(tariffsState.tributeCatalog);
  const periodRows = $derived(tariffDraft.periodRows as TributeDraftRow[]);
  const trafficRows = $derived(tariffDraft.trafficRows as TributeDraftRow[]);
  const subscriptionOptions = $derived(
    (tributeCatalog?.subscriptions || []).map((subscription) => ({
      value: String(subscription.subscription_id),
      label: subscriptionOptionLabel(subscription),
    }))
  );
  // The draft itself is the selection: reopening the editor for another tariff
  // then shows that tariff's binding instead of a stale local choice.
  const selectedSubscriptionId = $derived(
    String(periodRows.find((row) => row.tribute_subscription_id)?.tribute_subscription_id ?? "")
  );

  // A period left unbound looks exactly like one deliberately kept off Tribute,
  // so only the binding pass can report that the subscription lacks it.
  let missingPeriods = $state<TributeIssue[]>([]);

  function applyTributeSubscription(value: string): void {
    const subscription = (tributeCatalog?.subscriptions || []).find(
      (item) => String(item.subscription_id) === value
    );
    if (!subscription) return;
    const result = applySubscriptionToPeriodRows(subscription, periodRows, defaultCurrencyCode);
    for (const update of result.updates) {
      tariffsStore.updateDraftRow("periodRows", update.index, update.values);
    }
    missingPeriods = result.issues.filter((issue) => issue.kind === "missing_period");
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
              "Each row is a separate storefront option: how many days the user pays for and how much it costs. Drag rows by the handle to set the period order in the bot and the web app"
            )}</small
          >
        </div>
        <AdminButton size="sm" onclick={() => addPeriodRow()}>
          <Plus size={13} />
          {at("tariff_btn_period", {}, "Period")}
        </AdminButton>
      </header>
      <p class="admin-muted">
        {at(
          "tariff_period_days_hint",
          {},
          "30 days = 1 month; 365 days = 1 year. Other durations are shown in days."
        )}
      </p>
      <div class="admin-editor-section-actions">
        {#each [7, 14, 30, 90, 180, 365] as days (days)}
          <AdminButton
            size="sm"
            disabled={tariffDraft.periodRows.some((row) => Number(row.duration_days) === days)}
            onclick={() => addPeriodRow(days)}>{adminDurationLabel(days, at)}</AdminButton
          >
        {/each}
      </div>
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
            <span>{at("tariff_period_days", {}, "Period, days")}</span>
            <span>{currencyPriceColumnLabel}</span>
            <span>{at("tariff_col_price_stars_full", {}, "⭐ Stars")}</span>
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
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_period_days", {}, "Period, days")}</span
              >
              <Input
                class="input"
                type="number"
                min="1"
                placeholder="1"
                value={row.duration_days}
                title={adminDurationLabel(row.duration_days, at)}
                oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "duration_days")}
                aria-label={at("tariff_period_days", {}, "Period, days")}
              />
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{currencyPriceColumnLabel}</span
              >
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
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_col_price_stars_full", {}, "⭐ Stars")}</span
              >
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="150"
                value={row.stars}
                oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "stars")}
                aria-label={at("tariff_label_price_stars", {}, "⭐ Stars")}
              />
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_col_ref_inviter", {}, "Inviter bonus")}</span
              >
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
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_col_ref_referee", {}, "Friend bonus")}</span
              >
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

    {#if showTribute}
      <section class="admin-editor-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("tariff_tribute_title", {}, "Tribute subscription")}</strong>
            <small
              >{at(
                "tariff_tribute_subtitle",
                {},
                "Optional Creator fallback. Tribute publishes one subscription per offer, so each period below carries the link and IDs of the subscription that sells it. Tribute owns the price and the billing cycle; the local prices above are not sent to it"
              )}</small
            >
          </div>
          <div class="admin-editor-section-actions">
            <TributeCatalogButton {at} />
          </div>
        </header>
        {#if !tributeProviderEnabled}
          <p class="admin-muted">
            {at(
              "tariff_tribute_provider_off",
              {},
              "The Tribute provider is off. These fields are shown because the tariff still carries a mapping: clear them to drop it, or the saved catalog keeps referring to Tribute"
            )}
          </p>
        {/if}
        {#if tributeCatalog}
          <div class="admin-field-label">
            <span>{at("tariff_tribute_pick_subscription", {}, "Subscription in Tribute")}</span>
            <small
              >{at(
                "tariff_tribute_pick_subscription_hint",
                {},
                "Picking one fills the subscription and period IDs of every period below. The share link is not published by the API, so paste it yourself"
              )}</small
            >
            {#if subscriptionOptions.length}
              <AdminSelect
                value={selectedSubscriptionId}
                items={subscriptionOptions}
                placeholder={at("tariff_tribute_pick_placeholder", {}, "Select a subscription")}
                ariaLabel={at("tariff_tribute_pick_subscription", {}, "Subscription in Tribute")}
                onValueChange={applyTributeSubscription}
              />
            {:else}
              <span class="admin-muted"
                >{at(
                  "tariff_tribute_no_subscriptions",
                  {},
                  "Tribute has no published subscriptions on this API key"
                )}</span
              >
            {/if}
          </div>
        {/if}
        <TributeCatalogIssues {at} rows={periodRows} mode="period" extra={missingPeriods} />
        {#if tariffDraft.periodRows.length}
          <div class="admin-row-editor">
            <div
              class="admin-row-editor-line admin-row-editor-tribute-period admin-row-editor-header"
            >
              <span>{at("tariff_period_days", {}, "Period, days")}</span>
              <span>{at("tariff_col_tribute_link", {}, "Tribute subscription link")}</span>
              <span>{at("tariff_col_tribute_subscription_id", {}, "Tribute subscription ID")}</span>
              <span>{at("tariff_col_tribute_period_id", {}, "Tribute period ID")}</span>
            </div>
            {#each tariffDraft.periodRows as periodRow, index (index)}
              {@const row = periodRow as DraftRow}
              <div class="admin-row-editor-line admin-row-editor-tribute-period">
                <span class="admin-row-editor-static">
                  {adminDurationLabel(row.duration_days, at)}
                </span>
                <span class="admin-row-editor-mobile-label" aria-hidden="true"
                  >{at("tariff_col_tribute_link", {}, "Tribute subscription link")}</span
                >
                <Input
                  class="input"
                  type="url"
                  placeholder={at(
                    "tariff_placeholder_tribute_link",
                    {},
                    "https://t.me/tribute/app?startapp=..."
                  )}
                  value={row.tribute_link}
                  oninput={draftRowInputHandler(tariffsStore, "periodRows", index, "tribute_link")}
                  aria-label={at("tariff_label_tribute_link", {}, "Tribute subscription link")}
                />
                <span class="admin-row-editor-mobile-label" aria-hidden="true"
                  >{at("tariff_col_tribute_subscription_id", {}, "Tribute subscription ID")}</span
                >
                <Input
                  class="input"
                  type="number"
                  min="1"
                  step="1"
                  placeholder={at("tariff_placeholder_tribute_subscription_id", {}, "e.g. 101")}
                  value={row.tribute_subscription_id}
                  oninput={draftRowInputHandler(
                    tariffsStore,
                    "periodRows",
                    index,
                    "tribute_subscription_id"
                  )}
                  aria-label={at(
                    "tariff_label_tribute_subscription_id",
                    {},
                    "Tribute subscription ID"
                  )}
                />
                <span class="admin-row-editor-mobile-label" aria-hidden="true"
                  >{at("tariff_col_tribute_period_id", {}, "Tribute period ID")}</span
                >
                <Input
                  class="input"
                  type="number"
                  min="1"
                  step="1"
                  placeholder={at("tariff_placeholder_tribute_period_id", {}, "e.g. 1001")}
                  value={row.tribute_period_id}
                  oninput={draftRowInputHandler(
                    tariffsStore,
                    "periodRows",
                    index,
                    "tribute_period_id"
                  )}
                  aria-label={at("tariff_label_tribute_period_id", {}, "Tribute period ID")}
                />
              </div>
            {/each}
          </div>
          <p class="admin-muted">
            {at(
              "tariff_tribute_period_hint",
              {},
              "Leave a period empty to keep it off Tribute. Fill the link and both IDs for every period you sell through it"
            )}
          </p>
        {:else}
          <p class="admin-muted">
            {at(
              "tariff_pricing_empty",
              {},
              "Add at least one period so the tariff appears in the storefront."
            )}
          </p>
        {/if}
      </section>
    {/if}
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
          {#if showTribute}
            <TributeCatalogButton {at} />
          {/if}
          <AdminButton size="sm" onclick={addTrafficRow}
            ><Plus size={12} /> {at("tariff_btn_package", {}, "Package")}</AdminButton
          >
        </div>
      </header>
      {#if showTribute}
        <p class="admin-muted">
          {at(
            "tariff_tribute_products_hint",
            {},
            "Optional. Map each fixed traffic package to a Tribute Digital Product. Configure its price in Tribute to match this package; the local price is not sent to Tribute"
          )}
        </p>
        <TributeCatalogIssues {at} rows={trafficRows} mode="product" />
      {/if}
      {#if tariffDraft.trafficRows.length}
        <div class="admin-row-editor">
          <div
            class="admin-row-editor-line {showTribute
              ? 'admin-row-editor-tribute-product'
              : 'admin-row-editor-package'} admin-row-editor-header"
          >
            <span></span>
            <span>{at("tariff_col_volume_gb", {}, "Volume, GB")}</span>
            <span>{currencyPriceColumnLabel}</span>
            <span>{at("tariff_col_price_stars_full", {}, "⭐ Stars")}</span>
            {#if showTribute}
              <span>{at("tariff_col_tribute_product_id", {}, "Tribute product ID")}</span>
              <span>{at("tariff_col_tribute_product_link", {}, "Tribute product link")}</span>
            {/if}
            <span></span>
          </div>
          <Sortable
            items={tariffDraft.trafficRows}
            class={`admin-row-editor-line ${showTribute ? "admin-row-editor-tribute-product" : "admin-row-editor-package"}`}
            getKey={draftRowKey}
            handleLabel={at("tariff_package_reorder", {}, "Drag to reorder")}
            onReorder={moveTrafficRow}
          >
            {#snippet children(row: DraftRow, index: number)}
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_col_volume_gb", {}, "Volume, GB")}</span
              >
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
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{currencyPriceColumnLabel}</span
              >
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
              <span class="admin-row-editor-mobile-label" aria-hidden="true"
                >{at("tariff_col_price_stars_full", {}, "⭐ Stars")}</span
              >
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                placeholder="150"
                value={row.stars}
                oninput={draftRowInputHandler(tariffsStore, "trafficRows", index, "stars")}
                aria-label={at("tariff_label_price_stars", {}, "⭐ Stars")}
              />
              {#if showTribute}
                <span class="admin-row-editor-mobile-label" aria-hidden="true"
                  >{at("tariff_col_tribute_product_id", {}, "Tribute product ID")}</span
                >
                <TributeProductField {at} field="trafficRows" {index} {row} />
                <span class="admin-row-editor-mobile-label" aria-hidden="true"
                  >{at("tariff_col_tribute_product_link", {}, "Tribute product link")}</span
                >
                <Input
                  class="input"
                  type="url"
                  placeholder={at(
                    "tariff_placeholder_tribute_product_link",
                    {},
                    "https://t.me/tribute/app?startapp=..."
                  )}
                  value={row.tribute_product_link}
                  oninput={draftRowInputHandler(
                    tariffsStore,
                    "trafficRows",
                    index,
                    "tribute_product_link"
                  )}
                  aria-label={at("tariff_label_tribute_product_link", {}, "Tribute product link")}
                />
              {/if}
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

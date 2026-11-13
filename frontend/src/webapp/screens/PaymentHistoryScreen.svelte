<script lang="ts">
  import ScreenHeading from "$components/patterns/webapp/ScreenHeading.svelte";
  import ScreenBackLink from "$components/patterns/webapp/ScreenBackLink.svelte";
  import { onMount } from "svelte";
  import { CreditCardCheck, RefreshCw } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Badge from "$components/ui/badge.svelte";
  import { Tooltip } from "$components/ui/primitives.js";
  import {
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import PaymentProviderCell from "$components/patterns/admin/PaymentProviderCell.svelte";
  import PaymentPurchasesCell from "../../admin/sections/PaymentPurchasesCell.svelte";
  import {
    paymentAmountDisplay,
    paymentDescriptionDisplay,
    paymentDiscountDisplay,
    paymentPurchaseDisplay,
  } from "$lib/admin/paymentTable.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import { buildPaymentHistoryPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    paymentHistoryStatus,
    paymentHistoryTranslate,
    type PaymentHistoryItem,
  } from "$lib/webapp/paymentHistory.js";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    api,
    currentLang = "ru",
    goSettings,
    t,
  }: {
    api: ApiClient["api"];
    currentLang?: string;
    goSettings: VoidAction;
    t: Translate;
  } = $props();

  const pageSize = 10;
  let items = $state<PaymentHistoryItem[]>([]);
  let total = $state<number | null>(null);
  let page = $state(0);
  let loading = $state(true);
  let failed = $state(false);
  let openStatusTooltip = $state<number | null>(null);
  let listHeight = $state(0);
  let listWidth = $state(0);
  let reservation = $state({ width: 0, height: 0 });
  const reservedHeight = $derived(reservation.width === listWidth ? reservation.height : 0);
  let controller: AbortController | undefined;
  let requestSequence = 0;

  const pageCount = $derived(Math.max(1, Math.ceil((total ?? 0) / pageSize)));
  const hasPendingPayments = $derived(
    items.some((item) =>
      ["awaiting_payment", "processing", "crediting", "review"].includes(item.history_state)
    )
  );
  const at = $derived(paymentHistoryTranslate(t));
  const money = (amount: number, currency?: string | null) =>
    formatMoney(amount, currency || "RUB");
  const headers = $derived([
    t("wa_payment_history_id"),
    t("wa_payment_history_col_purchases"),
    t("wa_payment_history_amount"),
    t("wa_payment_history_col_discount"),
    t("wa_payment_history_provider"),
    t("wa_payment_history_description"),
    t("wa_payment_history_status"),
    t("wa_payment_history_date"),
  ]);

  function date(value: string | null | undefined): string {
    if (!value) return "—";
    const parsed = new Date(value);
    if (!Number.isFinite(parsed.getTime())) return "—";
    return new Intl.DateTimeFormat(currentLang, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(parsed);
  }

  async function loadPage(nextPage: number, quiet = false): Promise<void> {
    if (total !== null) {
      reservation = { width: listWidth, height: Math.max(reservedHeight, listHeight) };
    }
    const sequence = ++requestSequence;
    controller?.abort();
    controller = new AbortController();
    loading = !quiet;
    if (!quiet) openStatusTooltip = null;
    failed = false;
    try {
      const result = unwrap(
        await api(buildPaymentHistoryPath(pageSize, nextPage * pageSize), {
          signal: controller.signal,
        })
      );
      if (sequence !== requestSequence) return;
      if (result.total > 0 && result.offset >= result.total) {
        await loadPage(Math.max(0, Math.ceil(result.total / pageSize) - 1));
        return;
      }
      items = result.items;
      total = result.total;
      page = Math.floor(result.offset / pageSize);
    } catch {
      if (sequence === requestSequence && !controller.signal.aborted) failed = true;
    } finally {
      if (sequence === requestSequence) loading = false;
    }
  }

  onMount(() => {
    void loadPage(0);
    const refreshPending = () => {
      if (document.visibilityState === "visible" && hasPendingPayments && !loading)
        void loadPage(page, true);
    };
    const timer = window.setInterval(refreshPending, 15000);
    window.addEventListener("focus", refreshPending);
    document.addEventListener("visibilitychange", refreshPending);
    return () => {
      requestSequence += 1;
      controller?.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshPending);
      document.removeEventListener("visibilitychange", refreshPending);
    };
  });
</script>

<main class="content with-nav payment-history-screen">
  <ScreenBackLink label={t("wa_back")} onclick={goSettings} />
  <Card class="payment-history-heading">
    <ScreenHeading title={t("wa_payment_history_title")} subtitle={t("wa_payment_history_hint")}>
      {#snippet icon()}<CreditCardCheck />{/snippet}
    </ScreenHeading>
    <Button variant="secondary" size="sm" disabled={loading} onclick={() => void loadPage(page)}
      ><RefreshCw size={16} />{t("wa_payment_history_refresh")}</Button
    >
  </Card>

  <section
    class="payment-history-list"
    bind:clientHeight={listHeight}
    bind:clientWidth={listWidth}
    style:min-height={`${reservedHeight}px`}
    aria-label={t("wa_payment_history_title")}
    aria-busy={loading}
  >
    <div class="payment-history-content">
      {#if loading}
        <span class="payment-history-loading-label" role="status">{t("wa_loading")}</span>
        <div class="payment-history-skeleton" inert>
          <AdminTableSkeleton
            {headers}
            rows={items.length || 3}
            appearance="webapp"
            layout="fixed"
            minWidth="960px"
          />
        </div>
      {/if}
      <div class="payment-history-result" class:loading inert={loading}>
        {#if failed}
          <Card class="payment-history-state">
            <p role="alert">{t("wa_payment_history_load_failed")}</p>
            <Button variant="secondary" onclick={() => void loadPage(page)}>{t("wa_retry")}</Button>
          </Card>
        {:else if total === 0}
          <Card class="payment-history-empty">
            <CreditCardCheck size={32} />
            <h2>{t("wa_payment_history_empty")}</h2>
            <p>{t("wa_payment_history_empty_hint")}</p>
          </Card>
        {:else if items.length}
          <AdminTable appearance="webapp" layout="fixed" minWidth="960px">
            <colgroup>
              <col style="width: 82px" />
              <col style="width: 110px" />
              <col style="width: 90px" />
              <col style="width: 80px" />
              <col style="width: 105px" />
              <col style="width: 145px" />
              <col style="width: 178px" />
              <col style="width: 140px" />
            </colgroup>
            <thead
              ><tr
                >{#each headers as header (header)}<th scope="col">{header}</th>{/each}</tr
              ></thead
            >
            <tbody>
              {#each items as item (item.payment_id)}
                {@const status = paymentHistoryStatus(item, t)}
                {@const discount = paymentDiscountDisplay(item, money)}
                {@const description = paymentDescriptionDisplay(item, at)}
                <tr class="ph-row" data-payment-history-id={item.payment_id}>
                  <td class="ph-id" data-label={headers[0]} data-numeric
                    ><strong>#{item.payment_id}</strong></td
                  >
                  <td
                    class="ph-purchases"
                    data-label={headers[1]}
                    data-empty={paymentPurchaseDisplay(item, at).length ? undefined : ""}
                    ><PaymentPurchasesCell payment={item} {at} /></td
                  >
                  <td class="ph-amount" data-label={headers[2]} data-numeric
                    >{paymentAmountDisplay(item, money, at)}</td
                  >
                  <td
                    class="ph-discount"
                    data-label={headers[3]}
                    data-numeric
                    data-empty={discount === "—" ? "" : undefined}>{discount}</td
                  >
                  <td class="ph-provider" data-label={headers[4]}
                    ><PaymentProviderCell provider={item.provider} {at} /></td
                  >
                  <td
                    class="ph-description"
                    data-label={headers[5]}
                    data-empty={description === "—" ? "" : undefined}>{description}</td
                  >
                  <td class="ph-status" data-label={headers[6]}>
                    <Tooltip.Root
                      open={openStatusTooltip === item.payment_id}
                      onOpenChange={(open) => {
                        if (open) openStatusTooltip = item.payment_id;
                        else if (openStatusTooltip === item.payment_id) openStatusTooltip = null;
                      }}
                      delayDuration={180}
                      disableCloseOnTriggerClick={item.history_state !== "awaiting_payment" ||
                        !item.checkout_url}
                    >
                      {#if item.history_state === "awaiting_payment" && item.checkout_url}
                        <Tooltip.Trigger>
                          {#snippet child({ props })}
                            <a
                              {...props}
                              class="payment-history-status-trigger payment-history-checkout"
                              href={item.checkout_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              data-payment-history-checkout={item.payment_id}
                            >
                              <Badge wrap variant={status.variant}>{status.label}</Badge>
                            </a>
                          {/snippet}
                        </Tooltip.Trigger>
                      {:else}
                        <Tooltip.Trigger
                          class="payment-history-status-trigger"
                          type="button"
                          onclick={() => (openStatusTooltip = item.payment_id)}
                        >
                          <Badge wrap variant={status.variant}>{status.label}</Badge>
                        </Tooltip.Trigger>
                      {/if}
                      <Tooltip.Portal>
                        <Tooltip.Content
                          class="payment-method-tooltip"
                          role="tooltip"
                          side="top"
                          sideOffset={6}
                          collisionPadding={12}
                        >
                          {status.hint}
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  </td>
                  <td class="ph-date" data-label={headers[7]}>{date(item.created_at)}</td>
                </tr>
              {/each}
            </tbody>
          </AdminTable>
        {/if}
      </div>
    </div>
    {#if total !== null && total > 0}
      <AdminPagination
        appearance="webapp"
        {page}
        {pageCount}
        {total}
        disabled={loading}
        pageLabel={t("wa_partner_pagination_page")}
        ofLabel={t("wa_partner_pagination_of")}
        totalLabel={t("wa_partner_pagination_total")}
        jumpLabel={t("wa_partner_pagination_page")}
        jumpAriaLabel={t("wa_partner_pagination_jump")}
        goLabel={t("wa_partner_pagination_go")}
        prevLabel={t("wa_partner_pagination_previous")}
        nextLabel={t("wa_partner_pagination_next")}
        onPageChange={(nextPage) => void loadPage(nextPage)}
      />
    {/if}
  </section>
</main>

<style>
  .payment-history-screen {
    display: grid;
  }
  :global(.payment-history-heading) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }
  :global(.payment-history-heading .screen-heading) {
    flex: 1 1 260px;
  }
  :global(.payment-history-empty p) {
    margin: 6px 0 0;
    color: var(--muted);
    line-height: 1.5;
  }
  .payment-history-list {
    min-width: 0;
  }
  .payment-history-content {
    position: relative;
    min-height: 220px;
  }
  .payment-history-result.loading {
    visibility: hidden;
  }
  .payment-history-skeleton {
    position: absolute;
    inset: 0;
    overflow: hidden;
  }
  .payment-history-loading-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  :global(.payment-history-status-trigger) {
    display: inline-flex;
    max-width: 100%;
    padding: 0;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: help;
  }
  :global(.payment-history-status-trigger:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }
  :global(.payment-history-checkout) {
    text-decoration: none;
    cursor: pointer;
  }
  .payment-history-state,
  :global(.payment-history-state) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px;
  }
  :global(.payment-history-empty) {
    text-align: center;
    padding: 32px 20px;
  }
  :global(.payment-history-empty h2) {
    font-size: 18px;
  }
  /* Phones: one compact item per payment: number and amount on top, date and
     status under them, then what was bought; empty fields are hidden instead of
     printing eight label rows per payment. */
  @media (max-width: 720px) {
    :global(.payment-history-list .webapp-table-wrap tr.ph-row) {
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-areas:
        "id amount"
        "date status"
        "purchases purchases"
        "provider provider"
        "description description"
        "discount discount";
      gap: 6px 12px;
      padding: 12px 14px;
    }
    :global(.payment-history-list .webapp-table-wrap tr.ph-row > td) {
      display: block;
    }
    :global(.payment-history-list .webapp-table-wrap tr.ph-row > td::before) {
      display: none;
    }
    :global(.payment-history-list .webapp-table-wrap tr.ph-row > td[data-empty]) {
      display: none;
    }
    :global(.payment-history-list tr.ph-row > .ph-id) {
      grid-area: id;
    }
    :global(.payment-history-list tr.ph-row > .ph-amount) {
      grid-area: amount;
      justify-self: end;
      font-size: 15px;
      font-weight: 700;
    }
    :global(.payment-history-list tr.ph-row > .ph-date) {
      grid-area: date;
      align-self: center;
      color: var(--muted);
      font-size: 12px;
    }
    :global(.payment-history-list tr.ph-row > .ph-status) {
      grid-area: status;
      justify-self: end;
    }
    :global(.payment-history-list tr.ph-row > .ph-purchases) {
      grid-area: purchases;
    }
    :global(.payment-history-list tr.ph-row > .ph-provider) {
      grid-area: provider;
    }
    :global(.payment-history-list tr.ph-row > .ph-description) {
      grid-area: description;
      color: var(--muted);
      font-size: 12px;
    }
    :global(.payment-history-list tr.ph-row > .ph-discount) {
      grid-area: discount;
      color: var(--muted);
      font-size: 12px;
    }
    :global(.payment-history-list .webapp-table-wrap tr.ph-row > .ph-discount::before) {
      display: inline;
      content: attr(data-label) ": ";
    }
  }
</style>

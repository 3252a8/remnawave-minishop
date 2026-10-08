<script lang="ts">
  import { onMount } from "svelte";
  import { ArrowLeft, CreditCardCheck, RefreshCw } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Badge from "$components/ui/badge.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { Tooltip } from "$components/ui/primitives.js";
  import { AdminPagination, AdminTable } from "$components/patterns/admin/index.js";
  import PaymentProviderCell from "$components/patterns/admin/PaymentProviderCell.svelte";
  import PaymentPurchasesCell from "../../admin/sections/PaymentPurchasesCell.svelte";
  import { paymentDescriptionDisplay, paymentDiscountDisplay } from "$lib/admin/paymentTable.js";
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
    const sequence = ++requestSequence;
    controller?.abort();
    controller = new AbortController();
    loading = !quiet;
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
  <Button variant="ghost" size="sm" onclick={goSettings}>
    <ArrowLeft size={18} />{t("wa_back")}
  </Button>
  <Card class="payment-history-heading">
    <div class="payment-history-title">
      <CreditCardCheck size={30} />
      <div>
        <h1>{t("wa_payment_history_title")}</h1>
        <p>{t("wa_payment_history_hint")}</p>
      </div>
    </div>
    <Button variant="secondary" size="sm" disabled={loading} onclick={() => void loadPage(page)}
      ><RefreshCw size={16} />{t("wa_payment_history_refresh")}</Button
    >
  </Card>

  <section
    class="payment-history-list"
    aria-label={t("wa_payment_history_title")}
    aria-busy={loading}
  >
    {#if loading}
      <div class="payment-history-state" role="status">
        <Spinner /><span>{t("wa_loading")}</span>
      </div>
    {/if}
    {#if failed}
      <Card class="payment-history-state">
        <p role="alert">{t("wa_payment_history_load_failed")}</p>
        <Button variant="secondary" onclick={() => void loadPage(page)}>{t("wa_retry")}</Button>
      </Card>
    {/if}
    {#if !loading && !failed && total === 0}
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
            <tr data-payment-history-id={item.payment_id}>
              <td data-label={headers[0]} data-numeric><strong>#{item.payment_id}</strong></td>
              <td data-label={headers[1]}><PaymentPurchasesCell payment={item} {at} /></td>
              <td data-label={headers[2]} data-numeric>{money(item.amount, item.currency)}</td>
              <td data-label={headers[3]} data-numeric>{paymentDiscountDisplay(item, money)}</td>
              <td data-label={headers[4]}><PaymentProviderCell provider={item.provider} {at} /></td>
              <td data-label={headers[5]}>{paymentDescriptionDisplay(item, at)}</td>
              <td data-label={headers[6]}>
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
              <td data-label={headers[7]}>{date(item.created_at)}</td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    {/if}
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
    gap: 16px;
  }
  .payment-history-screen > :global(.btn) {
    justify-self: start;
  }
  :global(.payment-history-heading) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }
  .payment-history-title {
    display: flex;
    align-items: center;
    gap: 14px;
    flex: 1;
    min-width: 0;
  }
  .payment-history-title :global(svg) {
    flex: none;
    color: var(--accent);
  }
  .payment-history-title h1 {
    margin: 0;
    font-size: 22px;
  }
  .payment-history-title p,
  :global(.payment-history-empty p) {
    margin: 6px 0 0;
    color: var(--muted);
    line-height: 1.5;
  }
  .payment-history-list {
    min-width: 0;
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
  @media (max-width: 720px) {
    .payment-history-title h1 {
      font-size: 20px;
    }
    .payment-history-title {
      flex-basis: 100%;
    }
  }
</style>

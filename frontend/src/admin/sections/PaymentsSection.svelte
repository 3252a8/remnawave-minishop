<script lang="ts">
  import { getContext, onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { FileText, User } from "$components/ui/icons.js";
  import {
    createAdminDatatable,
    syncAdminDatatable,
    watchAdminDatatable,
  } from "../../lib/admin/datatables.js";
  import type { PaymentOut, PaymentsStore } from "../../lib/admin/stores/paymentsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  export let at: TranslateFn = (key) => key;
  export let fmtDate: (value: string | null | undefined) => string = (value) => String(value || "");
  export let fmtMoney: (value: number, currency?: string | null) => string = (value) =>
    String(value);
  export let paymentStatusVariant: (status: string | null | undefined) => string = () => "muted";
  export let onOpenUserCard: (userId: number) => void = () => {};

  const paymentsStore = getContext<PaymentsStore>("paymentsStore");
  const paymentsTable = createAdminDatatable();
  const paymentsTableSignal = watchAdminDatatable(paymentsTable);
  const PAYMENTS_PAGE_SIZE = 25;
  let payments: PaymentOut[] = [];
  let paymentsTotal = 0;
  let paymentsPage = 0;
  let paymentsLoading = false;

  $: ({ payments, paymentsTotal, paymentsPage, paymentsLoading } = $paymentsStore);
  $: syncAdminDatatable(paymentsTable, payments);

  $: paymentsPageCount = Math.max(1, Math.ceil(Number(paymentsTotal || 0) / PAYMENTS_PAGE_SIZE));

  function formatTrafficGbCell(v: number | string | null | undefined): string {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    let s;
    if (Math.abs(n - Math.round(n)) < 1e-9) {
      s = String(Math.round(n));
    } else {
      s = String(Math.round(n * 100) / 100);
    }
    return `${s} GB`;
  }

  function formatGbAmountPlain(v: number | string | null | undefined): string {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (Number.isNaN(n)) return "";
    if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
    return String(Math.round(n * 100) / 100);
  }

  function paymentDescriptionDisplay(p: PaymentOut): string {
    const r = p.traffic_regular_gb;
    const pr = p.traffic_premium_gb;
    if (r != null && pr == null) {
      const gb = formatGbAmountPlain(r);
      return at(
        "payments_desc_traffic_package_regular",
        { gb },
        `Пакет трафика ${gb} ГБ (обычный)`
      );
    }
    if (pr != null && r == null) {
      const gb = formatGbAmountPlain(pr);
      return at(
        "payments_desc_traffic_package_premium",
        { gb },
        `Пакет трафика ${gb} ГБ (премиум)`
      );
    }
    const raw = p.description && String(p.description).trim();
    return raw || "—";
  }

  $: paymentHeaders = [
    at("id", {}, "ID"),
    at("user", {}, "Пользователь"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "Основной трафик"),
    at("payments_col_traffic_premium", {}, "Премиум"),
    at("amount", {}, "Сумма"),
    at("provider", {}, "Провайдер"),
    at("description", {}, "Описание"),
    at("status", {}, "Статус"),
    at("date", {}, "Дата"),
  ];

  onMount(() => {
    paymentsStore.loadPayments();
  });
</script>

<div class="admin-table-wrap">
  {#if paymentsLoading}
    <AdminTableSkeleton
      headers={paymentHeaders}
      rows={8}
      widths={["48px", "148px", "88px", "72px", "72px", "78px", "82px", "140px", "72px", "96px"]}
    />
  {:else if !$paymentsTableSignal.rows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("payments_empty", {}, "Нет платежей")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <th>{at("id", {}, "ID")}</th>
          <th>{at("user", {}, "Пользователь")}</th>
          <th>{at("payments_col_user_id", {}, "ID")}</th>
          <th>{at("payments_col_traffic_regular", {}, "Основной трафик")}</th>
          <th>{at("payments_col_traffic_premium", {}, "Премиум")}</th>
          <th>{at("amount", {}, "Сумма")}</th>
          <th>{at("provider", {}, "Провайдер")}</th>
          <th>{at("description", {}, "Описание")}</th>
          <th>{at("status", {}, "Статус")}</th>
          <th>{at("date", {}, "Дата")}</th>
        </tr>
      </thead>
      <tbody>
        {#each $paymentsTableSignal.rows as p (p.payment_id)}
          <tr>
            <td class="admin-cell-id" data-label="ID">
              <AdminButton
                class="admin-payment-id-btn"
                variant="ghost"
                size="sm"
                title={at("payment_detail_open", {}, "Открыть платеж")}
                aria-label={at("payment_detail_open", {}, "Открыть платеж")}
                onclick={() => paymentsStore.openPayment(p)}
              >
                <FileText size={14} />
                #{p.payment_id}
              </AdminButton>
            </td>
            <td class="admin-cell-user-with-action" data-label={at("user", {}, "Пользователь")}>
              <span class="admin-payments-user-cell">
                <AdminButton
                  class="admin-payments-user-btn"
                  variant="ghost"
                  size="icon"
                  title={at("payments_open_user", {}, "Открыть карточку пользователя")}
                  aria-label={at("payments_open_user", {}, "Открыть карточку пользователя")}
                  onclick={() => onOpenUserCard(p.user_id)}
                >
                  <User size={14} />
                </AdminButton>
                <span class="admin-payments-user-name">{p.user_label || p.user_id}</span>
              </span>
            </td>
            <td class="admin-cell-mono" data-label={at("payments_col_user_id", {}, "ID")}>
              {p.user_id != null && p.user_id !== "" ? p.user_id : "—"}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_regular", {}, "Основной трафик")}
            >
              {formatTrafficGbCell(p.traffic_regular_gb)}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_premium", {}, "Премиум")}
            >
              {formatTrafficGbCell(p.traffic_premium_gb)}
            </td>
            <td data-label={at("amount", {}, "Сумма")}>{fmtMoney(p.amount, p.currency)}</td>
            <td data-label={at("provider", {}, "Провайдер")}>{p.provider}</td>
            <td class="admin-cell-wrap" data-label={at("description", {}, "Описание")}
              >{paymentDescriptionDisplay(p)}</td
            >
            <td data-label={at("status", {}, "Статус")}>
              <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
            </td>
            <td data-label={at("date", {}, "Дата")}>{fmtDate(p.created_at)}</td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  page={paymentsPage}
  pageCount={paymentsPageCount}
  total={paymentsTotal}
  pageLabel={at("page_short", {}, "Стр.")}
  ofLabel={at("pagination_of", {}, "из")}
  totalLabel={at("total", {}, "Всего")}
  jumpLabel={at("page_short", {}, "Стр.")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
  goLabel={at("pagination_go", {}, "Перейти")}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  onPageChange={(page) => paymentsStore.setPage(page)}
/>

<style>
  .admin-payments-user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-payments-user-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-cell-user-with-action :global(.admin-payments-user-btn.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
  }

  .admin-cell-user-with-action :global(.admin-payments-user-btn svg) {
    width: 14px;
    height: 14px;
  }

  .admin-cell-id :global(.admin-payment-id-btn.admin-btn) {
    height: 28px;
    min-height: 28px;
    padding: 0 8px;
    gap: 6px;
    border-radius: 7px;
    color: var(--admin-text);
    font-family: var(--font-mono);
    font-size: 12px;
  }
</style>

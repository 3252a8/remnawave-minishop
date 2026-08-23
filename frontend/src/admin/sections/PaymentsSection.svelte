<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminCopyableValue,
    AdminEmptyState,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
    VirtualTableRows,
  } from "$components/patterns/admin/index.js";
  import { FileText, User } from "$components/ui/icons.js";
  import { Popover } from "$components/ui/primitives.js";
  import { TableHandler } from "@vincjo/datatables";
  import {
    formatPaymentTrafficGb,
    paymentDescriptionDisplay,
    paymentDiscountDisplay,
  } from "$lib/admin/paymentTable.js";
  import type { PaymentOut } from "../../lib/admin/stores/paymentsStore";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";
  import PaymentProviderCell from "./PaymentProviderCell.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at = (key) => key,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (value) => String(value),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at?: TranslateFn;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (value: number, currency?: string | null) => string;
    paymentStatusVariant?: (status: string | null | undefined) => AdminBadgeVariant;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  const paymentsTable = new TableHandler<PaymentOut>();
  const PAYMENTS_PAGE_SIZE = 25;
  const payments = $derived(paymentsStore.payments as PaymentOut[]);
  const paymentsTotal = $derived(Number(paymentsStore.paymentsTotal || 0));
  const paymentsPage = $derived(Number(paymentsStore.paymentsPage || 0));
  const paymentsSort = $derived(String(paymentsStore.paymentsSort || "date_desc"));
  const paymentsLoading = $derived(Boolean(paymentsStore.paymentsLoading));

  function copyLabel(value: unknown): string {
    return at("copy_value", { value }, "Copy {value}");
  }

  function copyValue(value: unknown): void {
    paymentsStore.copyToClipboard(value, at("value_copied", {}, "Value copied"));
  }

  $effect(() => paymentsTable.setRows(payments));

  const paymentsPageCount = $derived(
    Math.max(1, Math.ceil(Number(paymentsTotal || 0) / PAYMENTS_PAGE_SIZE))
  );

  const paymentHeaders = $derived([
    at("id", {}, "ID"),
    at("user", {}, "User"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "Main traffic"),
    at("payments_col_traffic_premium", {}, "Premium traffic"),
    at("amount", {}, "Amount"),
    at("payments_col_discount", {}, "Discount"),
    at("provider", {}, "Provider"),
    at("description", {}, "Description"),
    at("status", {}, "Status"),
    at("date", {}, "Date"),
  ]);
  const paymentSortColumns = [
    { asc: "id_asc", desc: "id_desc", defaultDirection: "desc" },
    { asc: "user_asc", desc: "user_desc", defaultDirection: "asc" },
    { asc: "user_id_asc", desc: "user_id_desc", defaultDirection: "desc" },
    { asc: "traffic_regular_asc", desc: "traffic_regular_desc", defaultDirection: "desc" },
    { asc: "traffic_premium_asc", desc: "traffic_premium_desc", defaultDirection: "desc" },
    { asc: "amount_asc", desc: "amount_desc", defaultDirection: "desc" },
    { asc: "discount_asc", desc: "discount_desc", defaultDirection: "desc" },
    { asc: "provider_asc", desc: "provider_desc", defaultDirection: "asc" },
    { asc: "description_asc", desc: "description_desc", defaultDirection: "asc" },
    { asc: "status_asc", desc: "status_desc", defaultDirection: "asc" },
    { asc: "date_asc", desc: "date_desc", defaultDirection: "desc" },
  ] satisfies AdminSortColumn<never>[];

  onMount(() => {
    paymentsStore.loadPayments();
  });
</script>

<div class="admin-payments-table-shell">
  {#if paymentsLoading}
    <AdminTableSkeleton
      headers={paymentHeaders}
      rows={8}
      rowHeight={62}
      widths={[
        "48px",
        "148px",
        "88px",
        "72px",
        "72px",
        "78px",
        "92px",
        "82px",
        "140px",
        "72px",
        "96px",
      ]}
    />
  {:else if !paymentsTable.rows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("payments_empty", {}, "No payments")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable class="admin-payments-table">
      <colgroup>
        <col class="admin-payments-col-id" />
        <col class="admin-payments-col-user" />
        <col class="admin-payments-col-user-id" />
        <col class="admin-payments-col-traffic" />
        <col class="admin-payments-col-traffic" />
        <col class="admin-payments-col-amount" />
        <col class="admin-payments-col-discount" />
        <col class="admin-payments-col-provider" />
        <col class="admin-payments-col-description" />
        <col class="admin-payments-col-status" />
        <col class="admin-payments-col-date" />
      </colgroup>
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("id", {}, "ID")}
            column={paymentSortColumns[0]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("user", {}, "User")}
            column={paymentSortColumns[1]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("payments_col_user_id", {}, "ID")}
            column={paymentSortColumns[2]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("payments_col_traffic_regular", {}, "Main traffic")}
            column={paymentSortColumns[3]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("payments_col_traffic_premium", {}, "Premium traffic")}
            column={paymentSortColumns[4]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("amount", {}, "Amount")}
            column={paymentSortColumns[5]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("payments_col_discount", {}, "Discount")}
            column={paymentSortColumns[6]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("provider", {}, "Provider")}
            column={paymentSortColumns[7]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("description", {}, "Description")}
            column={paymentSortColumns[8]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("status", {}, "Status")}
            column={paymentSortColumns[9]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("date", {}, "Date")}
            column={paymentSortColumns[10]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
        </tr>
      </thead>
      <VirtualTableRows
        rows={paymentsTable.rows}
        colspan={11}
        rowHeight={62}
        getKey={(p) => p.payment_id}
      >
        {#snippet children(p)}
          {@const userLabel = String(p.user_label || p.user_id)}
          <tr>
            <td class="admin-cell-id" data-label="ID">
              <span class="admin-payment-id-actions">
                <AdminButton
                  class="admin-payment-id-btn"
                  variant="ghost"
                  size="icon"
                  title={at("payment_detail_open", {}, "Open payment")}
                  aria-label={at("payment_detail_open", {}, "Open payment")}
                  onclick={() => paymentsStore.openPayment(p)}
                >
                  <FileText size={14} />
                </AdminButton>
                <AdminCopyableValue
                  value={p.payment_id}
                  text={`#${p.payment_id}`}
                  copyLabel={copyLabel(p.payment_id)}
                  kind="payment-id"
                  oncopy={copyValue}
                />
              </span>
            </td>
            <td class="admin-cell-user-with-action" data-label={at("user", {}, "User")}>
              <span class="admin-payments-user-cell">
                <AdminButton
                  class="admin-payments-user-btn"
                  variant="ghost"
                  size="icon"
                  title={at("payments_open_user", {}, "Open user card")}
                  aria-label={at("payments_open_user", {}, "Open user card")}
                  onclick={() => onOpenUserCard(p.user_id)}
                >
                  <User size={14} />
                </AdminButton>
                <Popover.Root>
                  <Popover.Trigger
                    class="admin-payments-user-name"
                    title={at("payments_show_full_user", {}, "Show full user name")}
                    aria-label={at(
                      "payments_show_full_user_named",
                      { name: userLabel },
                      "Show full user name: {name}"
                    )}
                  >
                    {userLabel}
                  </Popover.Trigger>
                  <Popover.Portal>
                    <Popover.Content
                      class="admin-payments-user-popover"
                      side="bottom"
                      align="start"
                      sideOffset={6}
                    >
                      {userLabel}
                    </Popover.Content>
                  </Popover.Portal>
                </Popover.Root>
              </span>
            </td>
            <td class="admin-cell-mono" data-label={at("payments_col_user_id", {}, "ID")}>
              {#if p.user_id != null}
                <AdminCopyableValue
                  value={p.user_id}
                  copyLabel={copyLabel(p.user_id)}
                  kind="user-id"
                  oncopy={copyValue}
                />
              {:else}
                —
              {/if}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_regular", {}, "Main traffic")}
            >
              {formatPaymentTrafficGb(p.traffic_regular_gb)}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_premium", {}, "Premium traffic")}
            >
              {formatPaymentTrafficGb(p.traffic_premium_gb)}
            </td>
            <td data-label={at("amount", {}, "Amount")}>{fmtMoney(p.amount, p.currency)}</td>
            <td data-label={at("payments_col_discount", {}, "Discount")}>
              {paymentDiscountDisplay(p, fmtMoney)}
            </td>
            <td data-label={at("provider", {}, "Provider")}>
              <PaymentProviderCell provider={p.provider} />
            </td>
            <td class="admin-cell-wrap" data-label={at("description", {}, "Description")}
              >{paymentDescriptionDisplay(p, at)}</td
            >
            <td data-label={at("status", {}, "Status")}>
              <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
            </td>
            <td data-label={at("date", {}, "Date")}>{fmtDate(p.created_at)}</td>
          </tr>
        {/snippet}
      </VirtualTableRows>
    </AdminTable>

    <ul class="admin-payments-mobile-list">
      {#each paymentsTable.rows as p (p.payment_id)}
        {@const userLabel = String(p.user_label || p.user_id)}
        <li class="admin-payment-mobile-card" data-mobile-payment-id={p.payment_id}>
          <div class="admin-payment-mobile-head">
            <span class="admin-payment-id-actions">
              <AdminButton
                class="admin-payment-id-btn"
                variant="ghost"
                size="icon"
                title={at("payment_detail_open", {}, "Open payment")}
                aria-label={at("payment_detail_open", {}, "Open payment")}
                onclick={() => paymentsStore.openPayment(p)}
              >
                <FileText size={14} />
              </AdminButton>
              <AdminCopyableValue
                value={p.payment_id}
                text={`#${p.payment_id}`}
                copyLabel={copyLabel(p.payment_id)}
                kind="payment-id"
                oncopy={copyValue}
              />
            </span>
            <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
          </div>

          <div class="admin-payment-mobile-user">
            <AdminButton
              class="admin-payments-user-btn"
              variant="ghost"
              size="icon"
              title={at("payments_open_user", {}, "Open user card")}
              aria-label={at("payments_open_user", {}, "Open user card")}
              onclick={() => onOpenUserCard(p.user_id)}
            >
              <User size={14} />
            </AdminButton>
            <span class="admin-payment-mobile-user-copy">
              <strong>{userLabel}</strong>
              <small>
                <AdminCopyableValue
                  value={p.user_id}
                  text={`ID ${p.user_id}`}
                  copyLabel={copyLabel(p.user_id)}
                  kind="user-id"
                  oncopy={copyValue}
                />
              </small>
            </span>
            <time datetime={p.created_at || undefined}>{fmtDate(p.created_at)}</time>
          </div>

          <dl class="admin-payment-mobile-metrics">
            <div>
              <dt>{at("amount", {}, "Amount")}</dt>
              <dd>{fmtMoney(p.amount, p.currency)}</dd>
            </div>
            <div>
              <dt>{at("payments_col_discount", {}, "Discount")}</dt>
              <dd>{paymentDiscountDisplay(p, fmtMoney)}</dd>
            </div>
            <div>
              <dt>{at("payments_col_traffic_regular", {}, "Main traffic")}</dt>
              <dd>{formatPaymentTrafficGb(p.traffic_regular_gb)}</dd>
            </div>
            <div>
              <dt>{at("payments_col_traffic_premium", {}, "Premium traffic")}</dt>
              <dd>{formatPaymentTrafficGb(p.traffic_premium_gb)}</dd>
            </div>
          </dl>

          <div class="admin-payment-mobile-foot">
            <PaymentProviderCell provider={p.provider} />
            <span>{paymentDescriptionDisplay(p, at)}</span>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<AdminPagination
  page={paymentsPage}
  pageCount={paymentsPageCount}
  total={paymentsTotal}
  pageLabel={at("page_short", {}, "Page")}
  ofLabel={at("pagination_of", {}, "of")}
  totalLabel={at("total", {}, "Total")}
  jumpLabel={at("page_short", {}, "Page")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
  goLabel={at("pagination_go", {}, "Go")}
  prevLabel={at("back", {}, "Back")}
  nextLabel={at("next", {}, "Next")}
  onPageChange={(page) => paymentsStore.setPage(page)}
/>

<style>
  .admin-payments-table-shell {
    min-width: 0;
  }

  .admin-payments-table-shell :global(.admin-table-wrap) {
    overflow-x: auto;
  }

  .admin-payments-table-shell :global(.admin-payments-table) {
    min-width: 1360px;
    table-layout: fixed;
  }

  .admin-payments-mobile-list {
    display: none;
  }

  .admin-payments-table-shell :global(.admin-payments-col-id) {
    width: 118px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-user) {
    width: 230px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-user-id) {
    width: 170px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-traffic) {
    width: 112px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-amount) {
    width: 112px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-discount) {
    width: 100px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-provider) {
    width: 128px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-description) {
    width: 190px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-status) {
    width: 110px;
  }

  .admin-payments-table-shell :global(.admin-payments-col-date) {
    width: 150px;
  }

  .admin-payments-user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  :global(.admin-payments-user-name) {
    display: block;
    min-width: 0;
    max-width: 100%;
    margin: 0;
    padding: 2px 0;
    overflow: hidden;
    border: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font: inherit;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.admin-payments-user-name:hover),
  :global(.admin-payments-user-name:focus-visible) {
    color: var(--accent);
  }

  :global(.admin-payments-user-name:focus-visible) {
    outline: 2px solid color-mix(in srgb, var(--accent) 65%, transparent);
    outline-offset: 2px;
    border-radius: 4px;
  }

  :global(.admin-payments-user-popover) {
    z-index: 1200;
    max-width: min(440px, calc(100vw - 24px));
    padding: 10px 12px;
    overflow-wrap: anywhere;
    border: 1px solid var(--admin-border);
    border-radius: 9px;
    background: var(--admin-surface);
    box-shadow: var(--admin-card-shadow);
    color: var(--admin-text);
    font-size: 13px;
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

  .admin-payment-id-actions {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }

  .admin-payment-id-actions :global(.admin-copyable-value) {
    font-family: var(--font-mono);
    font-size: 12px;
  }

  @media (max-width: 720px) {
    .admin-payments-table-shell :global(.admin-table-wrap) {
      overflow-x: hidden;
    }

    .admin-payments-table-shell :global(.admin-payments-table) {
      display: none;
    }

    .admin-payments-mobile-list {
      display: grid;
      gap: 10px;
      width: 100%;
      min-width: 0;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .admin-payment-mobile-card {
      display: grid;
      gap: 10px;
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--admin-border);
      border-radius: 12px;
      background: var(--admin-surface-2);
    }

    .admin-payment-mobile-head,
    .admin-payment-mobile-user,
    .admin-payment-mobile-foot {
      min-width: 0;
      display: flex;
      align-items: center;
    }

    .admin-payment-mobile-head {
      justify-content: space-between;
      gap: 10px;
    }

    .admin-payment-mobile-user {
      gap: 9px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--admin-border);
    }

    .admin-payment-mobile-user-copy {
      display: grid;
      flex: 1 1 auto;
      gap: 2px;
      min-width: 0;
    }

    .admin-payment-mobile-user-copy strong,
    .admin-payment-mobile-user-copy small,
    .admin-payment-mobile-user time,
    .admin-payment-mobile-foot > span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .admin-payment-mobile-user-copy strong {
      color: var(--admin-text);
      font-size: 13px;
    }

    .admin-payment-mobile-user-copy small,
    .admin-payment-mobile-user time {
      color: var(--admin-muted);
      font-size: 11px;
    }

    .admin-payment-mobile-user-copy small {
      font-family: var(--font-mono);
    }

    .admin-payment-mobile-user time {
      flex: 0 1 auto;
      max-width: 42%;
      text-align: right;
    }

    .admin-payment-mobile-metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      min-width: 0;
      margin: 0;
    }

    .admin-payment-mobile-metrics > div {
      display: grid;
      gap: 3px;
      min-width: 0;
      padding: 8px 9px;
      border-radius: 8px;
      background: color-mix(in srgb, var(--admin-bg) 58%, transparent);
    }

    .admin-payment-mobile-metrics dt {
      overflow: hidden;
      color: var(--admin-muted);
      font-size: 10px;
      font-weight: 650;
      letter-spacing: 0.04em;
      text-overflow: ellipsis;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .admin-payment-mobile-metrics dd {
      min-width: 0;
      margin: 0;
      overflow-wrap: anywhere;
      color: var(--admin-text);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }

    .admin-payment-mobile-foot {
      gap: 9px;
      color: var(--admin-muted);
      font-size: 11px;
    }

    .admin-payment-mobile-foot > span {
      flex: 1 1 auto;
      min-width: 0;
    }

    .admin-payment-mobile-card :global(.admin-payment-id-btn.admin-btn) {
      height: 30px;
      min-height: 30px;
      padding: 0 8px;
    }

    .admin-payment-mobile-card :global(.admin-payments-user-btn.admin-btn) {
      width: 30px;
      height: 30px;
      min-width: 30px;
      min-height: 30px;
      flex: 0 0 auto;
      padding: 0;
    }
  }
</style>

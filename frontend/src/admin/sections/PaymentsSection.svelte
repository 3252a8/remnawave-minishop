<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
    VirtualTableRows,
  } from "$components/patterns/admin/index.js";
  import { FileText, User } from "$components/ui/icons.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { PaymentOut } from "../../lib/admin/stores/paymentsStore";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";

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

  $effect(() => paymentsTable.setRows(payments));

  const paymentsPageCount = $derived(
    Math.max(1, Math.ceil(Number(paymentsTotal || 0) / PAYMENTS_PAGE_SIZE))
  );

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
        `Traffic package ${gb} GB (standard)`
      );
    }
    if (pr != null && r == null) {
      const gb = formatGbAmountPlain(pr);
      return at(
        "payments_desc_traffic_package_premium",
        { gb },
        `Traffic package ${gb} GB (premium)`
      );
    }
    const raw = p.description && String(p.description).trim();
    return raw || "—";
  }

  const paymentHeaders = $derived([
    at("id", {}, "ID"),
    at("user", {}, "User"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "Main traffic"),
    at("payments_col_traffic_premium", {}, "Premium traffic"),
    at("amount", {}, "Amount"),
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
    { asc: "provider_asc", desc: "provider_desc", defaultDirection: "asc" },
    { asc: "description_asc", desc: "description_desc", defaultDirection: "asc" },
    { asc: "status_asc", desc: "status_desc", defaultDirection: "asc" },
    { asc: "date_asc", desc: "date_desc", defaultDirection: "desc" },
  ] satisfies AdminSortColumn<never>[];

  onMount(() => {
    paymentsStore.loadPayments();
  });
</script>

<div class="admin-table-wrap">
  {#if paymentsLoading}
    <AdminTableSkeleton
      headers={paymentHeaders}
      rows={8}
      rowHeight={62}
      widths={["48px", "148px", "88px", "72px", "72px", "78px", "82px", "140px", "72px", "96px"]}
    />
  {:else if !paymentsTable.rows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("payments_empty", {}, "No payments")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
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
            label={at("provider", {}, "Provider")}
            column={paymentSortColumns[6]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("description", {}, "Description")}
            column={paymentSortColumns[7]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("status", {}, "Status")}
            column={paymentSortColumns[8]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
          <AdminSortableHeader
            label={at("date", {}, "Date")}
            column={paymentSortColumns[9]}
            currentSort={paymentsSort}
            {at}
            onSort={paymentsStore.setSort}
          />
        </tr>
      </thead>
      <VirtualTableRows
        rows={paymentsTable.rows}
        colspan={10}
        rowHeight={62}
        getKey={(p) => p.payment_id}
      >
        {#snippet children(p)}
          <tr>
            <td class="admin-cell-id" data-label="ID">
              <AdminButton
                class="admin-payment-id-btn"
                variant="ghost"
                size="sm"
                title={at("payment_detail_open", {}, "Open payment")}
                aria-label={at("payment_detail_open", {}, "Open payment")}
                onclick={() => paymentsStore.openPayment(p)}
              >
                <FileText size={14} />
                #{p.payment_id}
              </AdminButton>
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
                <span class="admin-payments-user-name">{p.user_label || p.user_id}</span>
              </span>
            </td>
            <td class="admin-cell-mono" data-label={at("payments_col_user_id", {}, "ID")}>
              {p.user_id != null ? p.user_id : "—"}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_regular", {}, "Main traffic")}
            >
              {formatTrafficGbCell(p.traffic_regular_gb)}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_premium", {}, "Premium traffic")}
            >
              {formatTrafficGbCell(p.traffic_premium_gb)}
            </td>
            <td data-label={at("amount", {}, "Amount")}>{fmtMoney(p.amount, p.currency)}</td>
            <td data-label={at("provider", {}, "Provider")}>{p.provider}</td>
            <td class="admin-cell-wrap" data-label={at("description", {}, "Description")}
              >{paymentDescriptionDisplay(p)}</td
            >
            <td data-label={at("status", {}, "Status")}>
              <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
            </td>
            <td data-label={at("date", {}, "Date")}>{fmtDate(p.created_at)}</td>
          </tr>
        {/snippet}
      </VirtualTableRows>
    </AdminTable>
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

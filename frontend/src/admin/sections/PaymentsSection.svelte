<script lang="ts">
  import { getPaymentsStore } from "$lib/admin/context";
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
    VirtualTableRows,
  } from "$components/patterns/admin/index.js";
  import { FileText, User } from "$components/ui/icons.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { PaymentOut } from "../../lib/admin/stores/paymentsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at = (key) => key,
    fmtDate = (value) => String(value || ""),
    fmtMoney = (value) => String(value),
    paymentStatusLabel = (status) => String(status || "—"),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at?: TranslateFn;
    fmtDate?: (value: string | null | undefined) => string;
    fmtMoney?: (value: number, currency?: string | null) => string;
    paymentStatusLabel?: (status: string | null | undefined) => string;
    paymentStatusVariant?: (status: string | null | undefined) => string;
    onOpenUserCard?: (userId: number) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  const paymentsTable = new TableHandler<PaymentOut>();
  const PAYMENTS_PAGE_SIZE = 25;
  const payments = $derived(paymentsStore.payments as PaymentOut[]);
  const paymentsTotal = $derived(Number(paymentsStore.paymentsTotal || 0));
  const paymentsPage = $derived(Number(paymentsStore.paymentsPage || 0));
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
      return at("payments_desc_traffic_package_regular", { gb }, `流量套餐 ${gb}GB（普通）`);
    }
    if (pr != null && r == null) {
      const gb = formatGbAmountPlain(pr);
      return at("payments_desc_traffic_package_premium", { gb }, `流量套餐 ${gb}GB（高级）`);
    }
    if (r != null && pr != null) {
      const regularGb = formatGbAmountPlain(r);
      const premiumGb = formatGbAmountPlain(pr);
      return at(
        "payments_desc_traffic_package_mixed",
        { regularGb, premiumGb },
        `标准流量 ${regularGb} GB · 高级流量 ${premiumGb} GB`
      );
    }
    if (p.purchased_hwid_devices != null && Number(p.purchased_hwid_devices) > 0) {
      return at(
        "payments_desc_hwid_devices",
        { count: p.purchased_hwid_devices },
        `加购 HWID 设备 ${p.purchased_hwid_devices} 台`
      );
    }
    if (p.subscription_duration_months != null && Number(p.subscription_duration_months) > 0) {
      return at(
        "payments_desc_subscription_months",
        { count: p.subscription_duration_months },
        `订阅 ${p.subscription_duration_months} 个月`
      );
    }
    const raw = p.description && String(p.description).trim();
    return raw || "—";
  }

  const paymentHeaders = $derived([
    at("id", {}, "ID"),
    at("user", {}, "用户"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "基础流量"),
    at("payments_col_traffic_premium", {}, "高级流量"),
    at("amount", {}, "金额"),
    at("provider", {}, "支付方式"),
    at("description", {}, "描述"),
    at("status", {}, "状态"),
    at("date", {}, "日期"),
  ]);

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
  {:else if !paymentsTable.rows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("payments_empty", {}, "暂无支付记录")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <th>{at("id", {}, "ID")}</th>
          <th>{at("user", {}, "用户")}</th>
          <th>{at("payments_col_user_id", {}, "ID")}</th>
          <th>{at("payments_col_traffic_regular", {}, "基础流量")}</th>
          <th>{at("payments_col_traffic_premium", {}, "高级流量")}</th>
          <th>{at("amount", {}, "金额")}</th>
          <th>{at("provider", {}, "支付方式")}</th>
          <th>{at("description", {}, "描述")}</th>
          <th>{at("status", {}, "状态")}</th>
          <th>{at("date", {}, "日期")}</th>
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
                title={at("payment_detail_open", {}, "打开支付")}
                aria-label={at("payment_detail_open", {}, "打开支付")}
                onclick={() => paymentsStore.openPayment(p)}
              >
                <FileText size={14} />
                #{p.payment_id}
              </AdminButton>
            </td>
            <td class="admin-cell-user-with-action" data-label={at("user", {}, "用户")}>
              <span class="admin-payments-user-cell">
                <AdminButton
                  class="admin-payments-user-btn"
                  variant="ghost"
                  size="icon"
                  title={at("payments_open_user", {}, "打开用户详情")}
                  aria-label={at("payments_open_user", {}, "打开用户详情")}
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
              data-label={at("payments_col_traffic_regular", {}, "基础流量")}
            >
              {formatTrafficGbCell(p.traffic_regular_gb)}
            </td>
            <td
              class="admin-cell-traffic-gb"
              data-label={at("payments_col_traffic_premium", {}, "高级流量")}
            >
              {formatTrafficGbCell(p.traffic_premium_gb)}
            </td>
            <td data-label={at("amount", {}, "金额")}>{fmtMoney(p.amount, p.currency)}</td>
            <td data-label={at("provider", {}, "支付方式")}>{p.provider}</td>
            <td class="admin-cell-wrap" data-label={at("description", {}, "描述")}
              >{paymentDescriptionDisplay(p)}</td
            >
            <td data-label={at("status", {}, "状态")}>
              <AdminBadge variant={paymentStatusVariant(p.status)}>
                {paymentStatusLabel(p.status)}
              </AdminBadge>
            </td>
            <td data-label={at("date", {}, "日期")}>{fmtDate(p.created_at)}</td>
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
  pageLabel={at("page_short", {}, "页")}
  ofLabel={at("pagination_of", {}, "共")}
  totalLabel={at("total", {}, "共计")}
  jumpLabel={at("page_short", {}, "页")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "跳转到页面")}
  goLabel={at("pagination_go", {}, "前往")}
  prevLabel={at("back", {}, "上一步")}
  nextLabel={at("next", {}, "下一步")}
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

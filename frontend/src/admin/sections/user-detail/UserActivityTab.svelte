<script lang="ts">
  import { AdminBadge, AdminTable } from "$components/patterns/admin/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import { formatPaymentTrafficGb, paymentDescriptionDisplay } from "$lib/admin/paymentTable.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import PaymentProviderCell from "../PaymentProviderCell.svelte";
  import type { BadgeVariant, DateFormatter, MoneyFormatter, TranslateFn } from "./userDetailTypes";

  let {
    at,
    openedUserDetail,
    fmtMoney,
    fmtDateShort,
    paymentStatusVariant,
  }: {
    at: TranslateFn;
    openedUserDetail: AdminUserDetail;
    fmtMoney: MoneyFormatter;
    fmtDateShort: DateFormatter;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
  } = $props();
</script>

<Tabs.Content value="activity" class="admin-tabs-content">
  <div class="admin-subsection-title">
    {at(
      "user_recent_payments_title",
      { count: (openedUserDetail.recent_payments || []).length },
      "Recent Payments · {count}"
    )}
  </div>
  {#if (openedUserDetail.recent_payments || []).length}
    <div class="admin-user-payments-table">
      <AdminTable class="admin-table-compact admin-user-payments-table-grid">
        <thead>
          <tr>
            <th>{at("payments_col_traffic_regular", {}, "Main traffic")}</th>
            <th>{at("payments_col_traffic_premium", {}, "Premium traffic")}</th>
            <th>{at("amount", {}, "Amount")}</th>
            <th>{at("provider", {}, "Provider")}</th>
            <th>{at("description", {}, "Description")}</th>
            <th>{at("status", {}, "Status")}</th>
            <th>{at("date", {}, "Date")}</th>
          </tr>
        </thead>
        <tbody>
          {#each openedUserDetail.recent_payments as payment (payment.payment_id)}
            <tr>
              <td
                class="admin-cell-traffic-gb"
                data-label={at("payments_col_traffic_regular", {}, "Main traffic")}
              >
                {formatPaymentTrafficGb(payment.traffic_regular_gb)}
              </td>
              <td
                class="admin-cell-traffic-gb"
                data-label={at("payments_col_traffic_premium", {}, "Premium traffic")}
              >
                {formatPaymentTrafficGb(payment.traffic_premium_gb)}
              </td>
              <td data-label={at("amount", {}, "Amount")}>
                {fmtMoney(payment.amount, payment.currency)}
              </td>
              <td data-label={at("provider", {}, "Provider")}>
                <PaymentProviderCell provider={payment.provider} />
              </td>
              <td class="admin-cell-wrap" data-label={at("description", {}, "Description")}>
                {paymentDescriptionDisplay(payment, at)}
              </td>
              <td data-label={at("status", {}, "Status")}>
                <AdminBadge variant={paymentStatusVariant(payment.status)}>
                  {payment.status}
                </AdminBadge>
              </td>
              <td data-label={at("date", {}, "Date")}>{fmtDateShort(payment.created_at)}</td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    </div>
  {:else}
    <p class="admin-muted">{at("user_no_payments", {}, "No payments")}</p>
  {/if}
</Tabs.Content>

<style>
  .admin-user-payments-table {
    min-width: 0;
  }

  .admin-user-payments-table :global(.admin-table-wrap) {
    overflow-x: auto;
  }

  .admin-user-payments-table :global(.admin-user-payments-table-grid) {
    min-width: 760px;
  }

  @media (max-width: 720px) {
    .admin-user-payments-table :global(.admin-user-payments-table-grid) {
      min-width: 0;
    }
  }
</style>

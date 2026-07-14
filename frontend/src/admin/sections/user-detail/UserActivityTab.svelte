<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
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
    <div class="admin-mini-list">
      {#each openedUserDetail.recent_payments.slice(0, 8) as payment}
        <div class="admin-mini-list-row">
          <div>
            <strong>{fmtMoney(payment.amount, payment.currency)}</strong>
            <small>{payment.provider} · {fmtDateShort(payment.created_at)}</small>
          </div>
          <AdminBadge variant={paymentStatusVariant(payment.status)}>{payment.status}</AdminBadge>
        </div>
      {/each}
    </div>
  {:else}
    <p class="admin-muted">{at("user_no_payments", {}, "No payments")}</p>
  {/if}
</Tabs.Content>

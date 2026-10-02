<script lang="ts">
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { MoneyFormatter, TranslateFn } from "./userDetailTypes";
  let {
    at,
    openedUser,
    openedUserDetail,
    fmtMoney,
  }: {
    at: TranslateFn;
    openedUser: AdminUser;
    openedUserDetail: AdminUserDetail | null;
    fmtMoney: MoneyFormatter;
  } = $props();
  const balance = $derived(openedUserDetail?.balance);
  const hwidDevicesUsageLabel = $derived.by(() => {
    const current = openedUserDetail?.hwid_devices?.current_devices ?? "—";
    const limit = openedUserDetail?.hwid_devices?.max_devices;
    const max = limit != null && limit > 0 ? limit : "∞";
    return openedUserDetail?.hwid_devices
      ? at("user_hwid_devices_usage", { current, max }, "{current} / {max}")
      : "—";
  });
</script>

{#if openedUserDetail}
  <div class="admin-user-stats admin-user-stats-strip">
    <div class="admin-user-stat">
      <span>{at("user_label_paid", {}, "Total Paid")}</span><strong
        >{openedUserDetail.total_paid == null
          ? "—"
          : fmtMoney(openedUserDetail.total_paid, openedUser.payments_currency || "RUB")}</strong
      >
    </div>
    {#if balance?.enabled}
      <div class="admin-user-stat">
        <span>{at("user_label_balance", {}, "Balance")}</span><strong
          >{balance.amount == null ? "—" : fmtMoney(balance.amount, balance.currency)}</strong
        >
      </div>
    {/if}
    <div class="admin-user-stat">
      <span>{at("user_label_hwid_devices", {}, "HWID devices")}</span><strong
        >{hwidDevicesUsageLabel}</strong
      >
    </div>
    <div class="admin-user-stat">
      <span>{at("user_label_logs", {}, "Logs")}</span><strong
        >{openedUserDetail.log_count ?? "—"}</strong
      >
    </div>
  </div>
{/if}

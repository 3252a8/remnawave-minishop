<script lang="ts">
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { TranslateFn } from "./userDetailTypes";
  let {
    at,
    openedUserDetail,
    onEditNotifications,
  }: {
    at: TranslateFn;
    openedUserDetail: AdminUserDetail;
    onEditNotifications: () => void;
  } = $props();
  const notificationPreferences = $derived(
    openedUserDetail.notification_preferences ?? {
      marketing_email: true,
      marketing_telegram: true,
      system_email: true,
      system_telegram: true,
    }
  );

  function preferenceSummary(
    emailEnabled: boolean,
    telegramEnabled: boolean
  ): {
    label: string;
    variant: "success" | "warning" | "muted";
  } {
    if (emailEnabled && telegramEnabled) {
      return { label: at("user_notifications_on", {}, "On"), variant: "success" };
    }
    if (!emailEnabled && !telegramEnabled) {
      return { label: at("user_notifications_off", {}, "Off"), variant: "muted" };
    }
    return { label: at("user_notifications_partial", {}, "Partial"), variant: "warning" };
  }
  const marketingSummary = $derived(
    preferenceSummary(
      notificationPreferences.marketing_email,
      notificationPreferences.marketing_telegram
    )
  );
  const systemSummary = $derived(
    preferenceSummary(notificationPreferences.system_email, notificationPreferences.system_telegram)
  );
</script>

<section class="admin-user-notifications-summary">
  <div class="admin-subsection-title">{at("user_tab_notifications", {}, "Notifications")}</div>
  <div class="admin-user-preference-row">
    <span>{at("user_notifications_marketing_short", {}, "Marketing")}</span>
    <AdminBadge variant={marketingSummary.variant}>{marketingSummary.label}</AdminBadge>
  </div>
  <div class="admin-user-preference-row">
    <span>{at("user_notifications_system_short", {}, "System")}</span>
    <AdminBadge variant={systemSummary.variant}>{systemSummary.label}</AdminBadge>
  </div>
  <AdminButton size="sm" variant="ghost" onclick={onEditNotifications}>
    {at("user_notifications_edit", {}, "Edit")}
  </AdminButton>
</section>

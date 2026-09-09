<script lang="ts">
  import NotificationPreferencesPanel from "$components/patterns/NotificationPreferencesPanel.svelte";
  import { normalizeNotificationPreferences } from "$lib/webapp/notificationPreferences.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState.js";
  import type { TranslateFn, UsersStoreBridge } from "./userDetailTypes.js";

  let {
    at,
    usersStore,
    openedUserDetail,
    busy = false,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUserDetail: AdminUserDetail;
    busy?: boolean;
  } = $props();

  const preferences = $derived(
    normalizeNotificationPreferences(openedUserDetail.notification_preferences)
  );
</script>

<NotificationPreferencesPanel
  {preferences}
  disabled={busy}
  title={at("user_notifications_title", {}, "Notification preferences")}
  description={at(
    "user_notifications_hint",
    {},
    "These switches override delivery for this user without changing global notification settings."
  )}
  marketingLabel={at("user_notifications_marketing", {}, "News and offers")}
  marketingHint={at(
    "user_notifications_marketing_hint",
    {},
    "Admin broadcasts and automatic marketing campaigns"
  )}
  systemLabel={at("user_notifications_system", {}, "System notifications")}
  systemHint={at(
    "user_notifications_system_hint",
    {},
    "Payments, subscription expiration and renewal, traffic and devices"
  )}
  emailLabel={at("user_notifications_email", {}, "Email")}
  telegramLabel={at("user_notifications_telegram", {}, "Telegram")}
  note={at(
    "user_notifications_direct_note",
    {},
    "Personal messages sent by an administrator and security or support replies remain available."
  )}
  onChange={usersStore.updateUserNotificationPreferences}
/>

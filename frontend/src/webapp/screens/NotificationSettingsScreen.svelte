<script lang="ts">
  import { ArrowLeft, Megaphone } from "$components/ui/icons.js";
  import Card from "$components/ui/card.svelte";
  import NotificationPreferencesPanel from "$components/patterns/NotificationPreferencesPanel.svelte";
  import {
    normalizeNotificationPreferences,
    type NotificationPreferences,
  } from "$lib/webapp/notificationPreferences.js";
  import {
    buildAccountNotificationPreferencesPath,
    type ApiClient,
  } from "$lib/webapp/publicApi.js";
  import type { Translate, UserProfile, VoidAction } from "$lib/webapp/types.js";

  type Props = {
    api?: ApiClient["api"];
    goSettings?: VoidAction;
    t?: Translate;
    user?: UserProfile;
  };

  let { api = undefined, goSettings = () => {}, t = (key) => key, user = {} }: Props = $props();

  let notificationPreferences = $state<NotificationPreferences>(
    normalizeNotificationPreferences(null)
  );
  let notificationPreferencesBusy = $state(false);
  let notificationPreferencesStatus = $state("");
  let initializedNotificationUserId = $state<number | string | null>(null);

  $effect(() => {
    const userId = user?.id ?? null;
    if (userId !== initializedNotificationUserId) {
      initializedNotificationUserId = userId;
      notificationPreferences = normalizeNotificationPreferences(user?.notification_preferences);
    }
  });

  async function updateNotificationPreferences(next: NotificationPreferences): Promise<void> {
    if (notificationPreferencesBusy) return;
    const previous = notificationPreferences;
    notificationPreferences = next;
    notificationPreferencesStatus = "";
    if (!api) return;
    notificationPreferencesBusy = true;
    try {
      const response = await api(buildAccountNotificationPreferencesPath(), {
        method: "POST",
        body: JSON.stringify(next),
      });
      if (!response?.ok) throw response;
      notificationPreferences = normalizeNotificationPreferences(response.notification_preferences);
      user.notification_preferences = notificationPreferences;
      notificationPreferencesStatus = t(
        "wa_notification_preferences_saved",
        {},
        "Notification preferences saved"
      );
    } catch (_error) {
      notificationPreferences = previous;
      notificationPreferencesStatus = t(
        "wa_notification_preferences_save_failed",
        {},
        "Could not save notification preferences"
      );
    } finally {
      notificationPreferencesBusy = false;
    }
  }
</script>

<main class="content with-nav security-screen">
  <button class="security-back" type="button" onclick={goSettings}>
    <ArrowLeft size={19} />
    {t("wa_back")}
  </button>
  <Card class="security-overview-card">
    <div class="security-heading">
      <span><Megaphone size={32} /></span>
      <div>
        <h1>{t("wa_notification_preferences_title", {}, "Notifications")}</h1>
        <p>
          {t(
            "wa_notification_preferences_hint",
            {},
            "Choose separately what may be sent to your email and Telegram."
          )}
        </p>
      </div>
    </div>
  </Card>

  <NotificationPreferencesPanel
    preferences={notificationPreferences}
    disabled={notificationPreferencesBusy}
    title={t("wa_notification_preferences_delivery_title", {}, "Delivery settings")}
    description={t(
      "wa_notification_preferences_hint",
      {},
      "Choose separately what may be sent to your email and Telegram."
    )}
    marketingLabel={t("wa_notification_preferences_marketing", {}, "News and offers")}
    marketingHint={t(
      "wa_notification_preferences_marketing_hint",
      {},
      "Announcements, promotions and broadcast campaigns"
    )}
    systemLabel={t("wa_notification_preferences_system", {}, "System notifications")}
    systemHint={t(
      "wa_notification_preferences_system_hint",
      {},
      "Payments, subscription expiration and renewal, traffic and devices"
    )}
    emailLabel={t("wa_notification_preferences_email", {}, "Email")}
    telegramLabel={t("wa_notification_preferences_telegram", {}, "Telegram")}
    note={notificationPreferencesStatus ||
      t(
        "wa_notification_preferences_direct_note",
        {},
        "Personal administrator messages, security messages and support replies are always delivered."
      )}
    onChange={updateNotificationPreferences}
  />
</main>

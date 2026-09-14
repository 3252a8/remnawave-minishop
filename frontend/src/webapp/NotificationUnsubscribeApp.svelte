<script lang="ts">
  import { onMount } from "svelte";

  import Button from "$components/ui/button.svelte";
  import NotificationPreferencesPanel from "$components/patterns/NotificationPreferencesPanel.svelte";
  import { readJsonScript, normalizeBrand } from "$lib/webapp/browser.js";
  import { createI18n } from "$lib/webapp/i18n.js";
  import {
    DEFAULT_NOTIFICATION_PREFERENCES,
    normalizeNotificationPreferences,
    type NotificationPreferences,
  } from "$lib/webapp/notificationPreferences.js";
  import { buildApiUrl } from "$lib/webapp/publicApi.js";

  type RequestOptions = Parameters<typeof fetch>[1];
  type RequestFn = (path: string, options?: RequestOptions) => Promise<unknown>;
  type Props = {
    request?: RequestFn;
    brandTitle?: string;
    logoUrl?: string;
  };

  let { request = undefined, brandTitle = "", logoUrl = "" }: Props = $props();
  const injectedConfig = (readJsonScript("webapp-config") || {}) as Record<string, unknown>;
  const injectedMessages = (readJsonScript("i18n") || {}) as Record<string, unknown>;
  const brand = $derived(
    normalizeBrand({
      title: brandTitle || injectedConfig.title,
      logoUrl: logoUrl || injectedConfig.logoUrl || injectedConfig.logo_url,
    })
  );

  let language = $state("ru");
  const i18n = createI18n({
    messages: injectedMessages,
    getLang: () => language,
  });
  const token = new URLSearchParams(window.location.search).get("token") || "demo";
  let preferences = $state<NotificationPreferences>(DEFAULT_NOTIFICATION_PREFERENCES);
  let email = $state("");
  let loading = $state(true);
  let saving = $state(false);
  let success = $state(false);
  let error = $state("");

  const fallback = {
    title: "Manage email notifications",
    description: "Choose which emails you want to receive. You do not need to sign in.",
    marketing: "News and offers",
    marketingHint: "Promotions, announcements and broadcast campaigns",
    system: "System notifications",
    systemHint: "Payments, subscription expiration and renewal, traffic and devices",
    email: "Email",
    note: "Security messages and personal support replies cannot be disabled.",
    confirm: "Save preferences",
    success: "Email preferences for {email} have been saved",
    invalid: "This link is invalid or outdated. Open the link from a newer email.",
    loading: "Loading preferences…",
  };

  function text(key: string, value: string, params: Record<string, unknown> = {}): string {
    return i18n.t(key, params, value);
  }

  async function call(
    path: string,
    options: RequestOptions = {}
  ): Promise<Record<string, unknown>> {
    if (request) return (await request(path, options)) as Record<string, unknown>;
    const response = await fetch(buildApiUrl(path), {
      ...options,
      credentials: "omit",
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });
    return (await response.json()) as Record<string, unknown>;
  }

  async function load(): Promise<void> {
    loading = true;
    error = "";
    try {
      const response = await call(
        `/notification-preferences/unsubscribe?token=${encodeURIComponent(token)}`
      );
      if (!response.ok) throw response;
      email = String(response.email || "");
      language = String(response.language || language);
      preferences = normalizeNotificationPreferences(response.notification_preferences);
    } catch (_error) {
      error = text("wa_unsubscribe_invalid", fallback.invalid);
    } finally {
      loading = false;
    }
  }

  async function save(): Promise<void> {
    if (saving) return;
    saving = true;
    error = "";
    success = false;
    try {
      const response = await call("/notification-preferences/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          marketing_email: preferences.marketing_email,
          system_email: preferences.system_email,
        }),
      });
      if (!response.ok) throw response;
      email = String(response.email || email);
      preferences = normalizeNotificationPreferences(response.notification_preferences);
      success = true;
    } catch (_error) {
      error = text("wa_unsubscribe_invalid", fallback.invalid);
    } finally {
      saving = false;
    }
  }

  onMount(load);
</script>

<main class="unsubscribe-page">
  <section class="unsubscribe-shell">
    <header class="unsubscribe-brand">
      <img src={brand.logoUrl} alt="" />
      <strong>{brand.title}</strong>
    </header>

    {#if loading}
      <div class="unsubscribe-state">{text("wa_unsubscribe_loading", fallback.loading)}</div>
    {:else if error}
      <div class="unsubscribe-state unsubscribe-state--error">{error}</div>
    {:else}
      {#if email}<div class="unsubscribe-email">{email}</div>{/if}
      <NotificationPreferencesPanel
        {preferences}
        emailOnly
        disabled={saving}
        title={text("wa_unsubscribe_title", fallback.title)}
        description={text("wa_unsubscribe_hint", fallback.description)}
        marketingLabel={text("wa_notification_preferences_marketing", fallback.marketing)}
        marketingHint={text("wa_notification_preferences_marketing_hint", fallback.marketingHint)}
        systemLabel={text("wa_notification_preferences_system", fallback.system)}
        systemHint={text("wa_notification_preferences_system_hint", fallback.systemHint)}
        emailLabel={text("wa_notification_preferences_email", fallback.email)}
        telegramLabel="Telegram"
        note={text("wa_notification_preferences_direct_note", fallback.note)}
        onChange={(next) => {
          preferences = next;
          success = false;
        }}
      />
      <Button size="lg" disabled={saving} onclick={save}>
        {text("wa_unsubscribe_confirm", fallback.confirm)}
      </Button>
      {#if success}
        <div class="unsubscribe-state unsubscribe-state--success">
          {text("wa_unsubscribe_success", fallback.success, { email })}
        </div>
      {/if}
    {/if}
  </section>
</main>

<style>
  .unsubscribe-page {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 28px 16px;
    background: var(--background, #070a0e);
  }

  .unsubscribe-shell {
    display: grid;
    gap: 16px;
    width: min(100%, 620px);
  }

  .unsubscribe-brand {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--foreground, #f4f7fa);
  }

  .unsubscribe-brand img {
    width: 38px;
    height: 38px;
    object-fit: contain;
    border-radius: var(--radius-control);
  }

  .unsubscribe-brand strong {
    font-size: 18px;
  }

  .unsubscribe-email {
    justify-self: center;
    padding: 7px 11px;
    border: 1px solid var(--border, #26303b);
    border-radius: 999px;
    color: var(--muted-foreground, #9aa3b2);
    font-size: 12px;
  }

  .unsubscribe-state {
    padding: 14px 16px;
    border: 1px solid var(--border, #26303b);
    border-radius: var(--radius-card);
    color: var(--muted-foreground, #9aa3b2);
    text-align: center;
  }

  .unsubscribe-state--success {
    border-color: color-mix(in srgb, var(--primary, #00fe7a) 55%, transparent);
    color: var(--primary, #00fe7a);
  }

  .unsubscribe-state--error {
    border-color: #6f3038;
    color: #ff8793;
  }
</style>

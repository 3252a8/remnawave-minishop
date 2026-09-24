<script lang="ts">
  import {
    ArrowLeft,
    ArrowRight,
    CheckCircle2,
    Circle,
    Fingerprint,
    Key,
    Mail,
    Shield,
    Trash2,
  } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import { buildExternalOAuthStartUrl } from "$lib/webapp/authHelpers.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import { passkeyRegistrationBlockReason, registerPasskey } from "$lib/webapp/passkeys.js";
  import type { Translate, UserProfile, VoidAction } from "$lib/webapp/types.js";
  import ProviderLogo from "../auth/ProviderLogo.svelte";
  import ChangeEmailDialog from "../security/ChangeEmailDialog.svelte";

  type ExternalIdentity = {
    provider?: string;
    email?: string | null;
    display_name?: string | null;
    can_unlink?: boolean;
  };
  type Passkey = {
    credential_id?: string;
    name?: string;
    created_at?: string | null;
    last_used_at?: string | null;
    backed_up?: boolean;
    device_type?: string | null;
    transports?: string[];
  };
  type AccountEmailAddress = {
    email?: string;
    verified?: boolean;
    is_primary?: boolean;
    is_notification?: boolean;
    sources?: string[];
  };
  type Props = {
    api: ApiClient["api"];
    authProviders?: string[];
    brandTitle?: string;
    currentLang?: string;
    emailAuthEnabled?: boolean;
    emailChangeEnabled?: boolean;
    goSettings: VoidAction;
    linkTelegramAccount: VoidAction;
    openLinkEmailDialog: VoidAction;
    openSetPasswordDialog: VoidAction;
    openSubscriptionReissueDialog?: VoidAction;
    subscriptionReissueBusy?: boolean;
    subscriptionReissueVisible?: boolean;
    t: Translate;
    telegramMiniAppContext?: boolean;
    user?: UserProfile;
  };

  let {
    api,
    authProviders = [],
    brandTitle = "",
    currentLang = "ru",
    emailAuthEnabled = true,
    emailChangeEnabled = true,
    goSettings,
    linkTelegramAccount,
    openLinkEmailDialog,
    openSetPasswordDialog,
    openSubscriptionReissueDialog = () => {},
    subscriptionReissueBusy = false,
    subscriptionReissueVisible = false,
    t,
    telegramMiniAppContext = false,
    user = {},
  }: Props = $props();

  const externalIdentities = $derived((user.external_identities || []) as ExternalIdentity[]);
  const passkeys = $derived((user.passkeys || []) as Passkey[]);
  const emailAddresses = $derived((user.email_addresses || []) as AccountEmailAddress[]);
  const googleIdentity = $derived(externalIdentities.find((item) => item.provider === "google"));
  const yandexIdentity = $derived(externalIdentities.find((item) => item.provider === "yandex"));
  const discordIdentity = $derived(externalIdentities.find((item) => item.provider === "discord"));
  const passkeyEnabled = $derived(authProviders.includes("passkey"));
  const showPasskeys = $derived(passkeyEnabled || passkeys.length > 0);
  const googleVisible = $derived(authProviders.includes("google") || Boolean(googleIdentity));
  const yandexVisible = $derived(authProviders.includes("yandex") || Boolean(yandexIdentity));
  const discordVisible = $derived(authProviders.includes("discord") || Boolean(discordIdentity));
  const emailEnabled = $derived(
    emailAuthEnabled && (authProviders.includes("email") || Boolean(user.email))
  );
  const telegramEnabled = $derived(authProviders.includes("telegram"));
  let busy = $state(false);
  let status = $state("");
  let emailChangeOpen = $state(false);
  let selectedNotificationEmail = $state("");

  $effect(() => {
    if (!selectedNotificationEmail) {
      selectedNotificationEmail = String(user.notification_email || user.email || "");
    }
  });

  function externalLabel(identity: ExternalIdentity | undefined): string {
    return String(identity?.email || identity?.display_name || "");
  }

  function formatPasskeyDate(value: string | null | undefined): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    try {
      return new Intl.DateTimeFormat(currentLang, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
    } catch {
      return date.toLocaleString();
    }
  }

  function passkeyTransportLabel(transports: string[] | undefined): string {
    const labels = (transports || []).map((transport) => {
      if (transport === "internal") return t("wa_security_passkey_transport_internal");
      if (transport === "hybrid") return t("wa_security_passkey_transport_hybrid");
      if (transport === "usb") return "USB";
      if (transport === "nfc") return "NFC";
      if (transport === "ble") return "Bluetooth";
      return "";
    });
    return [...new Set(labels.filter(Boolean))].join(" · ");
  }

  function linkExternal(provider: "discord" | "google" | "yandex"): void {
    window.location.assign(buildExternalOAuthStartUrl(provider, "link", currentLang));
  }

  function emailAddressSources(address: AccountEmailAddress): string {
    const labels = (address.sources || []).map((source) => {
      if (source === "google") return "Google";
      if (source === "yandex") return "Yandex";
      if (source === "discord") return "Discord";
      return t("wa_security_email_source", {}, "Email");
    });
    if (address.is_primary) labels.push(t("wa_security_primary_email", {}, "Primary"));
    return [...new Set(labels)].join(" · ");
  }

  async function chooseNotificationEmail(email: string): Promise<void> {
    if (!email || email === selectedNotificationEmail) return;
    busy = true;
    status = "";
    try {
      const response = await api("/account/email/notification", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (!response.ok) throw response;
      selectedNotificationEmail = email;
      status = t("wa_security_notification_email_updated", {}, "Notification email updated");
    } catch {
      status = t(
        "wa_security_notification_email_failed",
        {},
        "Could not update notification email"
      );
    } finally {
      busy = false;
    }
  }

  async function unlinkExternal(provider: "discord" | "google" | "yandex"): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/identities/unlink", {
        method: "POST",
        body: JSON.stringify({ provider }),
      });
      if (!response.ok) throw response;
      window.location.reload();
    } catch {
      status = t(
        "wa_security_provider_unlink_failed",
        {},
        "Could not unlink the last available login method"
      );
    } finally {
      busy = false;
    }
  }

  async function addPasskey(): Promise<void> {
    const blocked = passkeyRegistrationBlockReason(telegramMiniAppContext);
    if (blocked) {
      status =
        blocked === "telegram_mini_app"
          ? t(
              "wa_security_passkey_browser_required",
              {},
              "Add passkeys from this site in a regular browser, not inside Telegram"
            )
          : t("wa_security_passkey_unsupported", {}, "Passkeys are not supported on this device");
      return;
    }
    busy = true;
    status = "";
    try {
      await registerPasskey(
        api,
        brandTitle || t("wa_security_passkey_default_name", {}, "Passkey")
      );
      window.location.reload();
    } catch (error) {
      status =
        error instanceof Error && error.message === "passkey_unsupported"
          ? t("wa_security_passkey_unsupported", {}, "Passkeys are not supported on this device")
          : t("wa_security_passkey_failed", {}, "Could not add the passkey");
    } finally {
      busy = false;
    }
  }

  async function removePasskey(credentialId: string): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/passkeys/delete", {
        method: "POST",
        body: JSON.stringify({ credential_id: credentialId }),
      });
      if (!response.ok) throw response;
      window.location.reload();
    } catch {
      status = t(
        "wa_security_passkey_delete_failed",
        {},
        "Could not remove the last available login method"
      );
    } finally {
      busy = false;
    }
  }

  $effect(() => {
    const value = new URLSearchParams(window.location.search).get("external_auth");
    if (!value) return;
    const [, result] = value.split(":", 2);
    status =
      result === "success"
        ? t("wa_security_provider_linked", {}, "Login provider linked")
        : t("wa_security_provider_failed", {}, "Could not link the login provider");
    const clean = new URL(window.location.href);
    clean.searchParams.delete("external_auth");
    window.history.replaceState(null, "", `${clean.pathname}${clean.search}${clean.hash}`);
  });
</script>

<main class="content with-nav security-screen">
  <button class="security-back" type="button" onclick={goSettings}>
    <ArrowLeft size={19} />
    {t("wa_back")}
  </button>
  <Card class="security-overview-card">
    <div class="security-heading">
      <span><Shield size={32} /></span>
      <div>
        <h1>{t("wa_security_title", {}, "Security")}</h1>
        <p>{t("wa_security_hint", {}, "Manage how you sign in and recover access")}</p>
      </div>
    </div>
  </Card>

  {#if subscriptionReissueVisible}
    <Card class="security-card">
      <h2>{t("wa_security_subscription_access", {}, "Subscription access")}</h2>
      <div class="settings-list">
        <button
          data-webapp-action="open-subscription-reissue"
          class="settings-row settings-row-subscription-reissue"
          type="button"
          onclick={openSubscriptionReissueDialog}
          disabled={subscriptionReissueBusy}
        >
          <Key size={21} />
          <span>
            <strong>{t("wa_subscription_reissue_action")}</strong>
            <small>{t("wa_settings_subscription_reissue_hint")}</small>
          </span>
          <ArrowRight size={17} />
        </button>
      </div>
    </Card>
  {/if}

  <Card class="security-card">
    <h2>{t("wa_security_login_methods", {}, "Login methods")}</h2>
    <div class="settings-list security-methods">
      {#if telegramEnabled}
        <button
          class="settings-row attention-wrap"
          type="button"
          onclick={user.telegram_linked ? undefined : linkTelegramAccount}
        >
          {#if !user.telegram_linked}<AttentionDot />{/if}
          <ProviderLogo provider="telegram" size={21} />
          <span>
            <strong>Telegram</strong>
            <small
              >{user.telegram_linked
                ? t("wa_settings_linked")
                : t("wa_settings_link_telegram_action")}</small
            >
          </span>
          {#if user.telegram_linked}<CheckCircle2 size={18} />{:else}<ArrowRight size={17} />{/if}
        </button>
      {/if}
      {#if emailEnabled}
        {#if user.email && !emailChangeEnabled}
          <div class="settings-row security-email-change-disabled">
            <Mail size={21} />
            <span>
              <strong>{user.email}</strong>
              <small>{t("wa_security_email_change_disabled")}</small>
            </span>
          </div>
        {:else}
          <button
            class="settings-row attention-wrap"
            type="button"
            onclick={user.email ? () => (emailChangeOpen = true) : openLinkEmailDialog}
            disabled={busy}
          >
            {#if !user.email}<AttentionDot />{/if}
            <Mail size={21} />
            <span>
              <strong>{user.email || t("wa_settings_link_email_action")}</strong>
              <small>{user.email ? t("wa_security_change_email", {}, "Change email") : ""}</small>
            </span>
            <ArrowRight size={17} />
          </button>
        {/if}
        {#if user.email_verified}
          <button class="settings-row" type="button" onclick={openSetPasswordDialog}>
            <Key size={21} />
            <span>
              <strong
                >{user.password_auth_enabled
                  ? t("wa_settings_change_password_action")
                  : t("wa_settings_set_password_action")}</strong
              >
              <small>{t("wa_security_password_hint", {}, "Email and password login")}</small>
            </span>
            <ArrowRight size={17} />
          </button>
        {/if}
      {/if}
      {#if googleVisible}
        {#if googleIdentity}
          <div class="settings-row security-deletable-row">
            <ProviderLogo provider="google" size={21} />
            <span><strong>Google</strong><small>{externalLabel(googleIdentity)}</small></span>
            {#if googleIdentity.can_unlink}
              <button
                class="security-delete"
                type="button"
                aria-label={t("wa_security_unlink_provider", {}, "Unlink provider")}
                onclick={() => unlinkExternal("google")}
                disabled={busy}><Trash2 size={17} /></button
              >
            {/if}
          </div>
        {:else}
          <button
            class="settings-row"
            type="button"
            onclick={() => linkExternal("google")}
            disabled={busy}
          >
            <ProviderLogo provider="google" size={21} />
            <span
              ><strong>Google</strong><small
                >{t("wa_security_link_provider", {}, "Link account")}</small
              ></span
            >
            <ArrowRight size={17} />
          </button>
        {/if}
      {/if}
      {#if yandexVisible}
        {#if yandexIdentity}
          <div class="settings-row security-deletable-row">
            <ProviderLogo provider="yandex" size={21} />
            <span><strong>Yandex</strong><small>{externalLabel(yandexIdentity)}</small></span>
            {#if yandexIdentity.can_unlink}
              <button
                class="security-delete"
                type="button"
                aria-label={t("wa_security_unlink_provider", {}, "Unlink provider")}
                onclick={() => unlinkExternal("yandex")}
                disabled={busy}><Trash2 size={17} /></button
              >
            {/if}
          </div>
        {:else}
          <button
            class="settings-row"
            type="button"
            onclick={() => linkExternal("yandex")}
            disabled={busy}
          >
            <ProviderLogo provider="yandex" size={21} />
            <span
              ><strong>Yandex</strong><small
                >{t("wa_security_link_provider", {}, "Link account")}</small
              ></span
            >
            <ArrowRight size={17} />
          </button>
        {/if}
      {/if}
      {#if discordVisible}
        {#if discordIdentity}
          <div class="settings-row security-deletable-row">
            <ProviderLogo provider="discord" size={21} />
            <span><strong>Discord</strong><small>{externalLabel(discordIdentity)}</small></span>
            {#if discordIdentity.can_unlink}
              <button
                class="security-delete"
                type="button"
                aria-label={t("wa_security_unlink_provider", {}, "Unlink provider")}
                onclick={() => unlinkExternal("discord")}
                disabled={busy}><Trash2 size={17} /></button
              >
            {/if}
          </div>
        {:else}
          <button
            class="settings-row"
            type="button"
            onclick={() => linkExternal("discord")}
            disabled={busy}
          >
            <ProviderLogo provider="discord" size={21} />
            <span
              ><strong>Discord</strong><small
                >{t("wa_security_link_provider", {}, "Link account")}</small
              ></span
            >
            <ArrowRight size={17} />
          </button>
        {/if}
      {/if}
    </div>
  </Card>

  {#if emailAuthEnabled && emailAddresses.length}
    <Card class="security-card">
      <div class="security-card-head">
        <div>
          <h2>{t("wa_security_notification_email", {}, "Notification email")}</h2>
          <p>
            {t(
              "wa_security_notification_email_hint",
              {},
              "Choose where account and subscription notifications are delivered"
            )}
          </p>
        </div>
      </div>
      <div class="settings-list security-email-addresses">
        {#each emailAddresses as address (address.email)}
          {@const addressEmail = String(address.email || "")}
          {@const selected = addressEmail === selectedNotificationEmail}
          <button
            class="settings-row security-notification-email-row"
            class:is-selected={selected}
            type="button"
            onclick={() => chooseNotificationEmail(addressEmail)}
            disabled={busy || !address.verified}
          >
            <span class="security-email-source-logos" aria-hidden="true">
              {#if address.sources?.includes("google")}
                <ProviderLogo provider="google" size={19} />
              {/if}
              {#if address.sources?.includes("yandex")}
                <ProviderLogo provider="yandex" size={19} />
              {/if}
              {#if address.sources?.includes("discord")}
                <ProviderLogo provider="discord" size={19} />
              {/if}
              {#if !address.sources?.some( (source) => ["discord", "google", "yandex"].includes(source) )}
                <Mail size={19} />
              {/if}
            </span>
            <span>
              <strong>{addressEmail}</strong>
              <small>{emailAddressSources(address)}</small>
            </span>
            {#if selected}<CheckCircle2 size={18} />{:else}<Circle size={18} />{/if}
          </button>
        {/each}
      </div>
    </Card>
  {/if}

  {#if showPasskeys}
    <Card class="security-card">
      <div class="security-card-head">
        <div>
          <h2>{t("wa_security_passkeys", {}, "Passkeys")}</h2>
          <p>{t("wa_security_passkeys_hint", {}, "Sign in with biometrics or your device PIN")}</p>
        </div>
        {#if passkeyEnabled}<Button size="sm" onclick={addPasskey} disabled={busy}
            ><Fingerprint size={16} />{t("wa_add")}</Button
          >{/if}
      </div>
      {#if passkeys.length}
        <div class="security-passkey-list">
          {#each passkeys as passkey (passkey.credential_id)}
            <div
              class="settings-row settings-row-linked security-deletable-row security-passkey-row"
            >
              <Fingerprint size={21} />
              <div class="security-passkey-content">
                <strong>{passkey.name || t("wa_security_passkey_default_name")}</strong>
                <div class="security-passkey-meta">
                  <small
                    >{passkey.backed_up || passkey.device_type === "multi_device"
                      ? t("wa_security_passkey_synced", {}, "Synced")
                      : t("wa_security_passkey_device", {}, "This device")}</small
                  >
                  {#if passkeyTransportLabel(passkey.transports)}
                    <small>{passkeyTransportLabel(passkey.transports)}</small>
                  {/if}
                  {#if formatPasskeyDate(passkey.created_at)}
                    <small
                      >{t("wa_security_passkey_created", {
                        date: formatPasskeyDate(passkey.created_at),
                      })}</small
                    >
                  {/if}
                  {#if formatPasskeyDate(passkey.last_used_at)}
                    <small
                      >{t("wa_security_passkey_last_used", {
                        date: formatPasskeyDate(passkey.last_used_at),
                      })}</small
                    >
                  {/if}
                </div>
              </div>
              <button
                class="security-delete"
                type="button"
                aria-label={t("wa_delete")}
                onclick={() => removePasskey(String(passkey.credential_id || ""))}
                disabled={busy}><Trash2 size={17} /></button
              >
            </div>
          {/each}
        </div>
      {:else}
        <p class="security-empty">{t("wa_security_no_passkeys", {}, "No passkeys added yet")}</p>
      {/if}
    </Card>
  {/if}
  {#if status}<p class="security-status" role="status">{status}</p>{/if}
</main>

{#if emailAuthEnabled && user.email}
  <ChangeEmailDialog
    {api}
    currentEmail={String(user.email)}
    open={emailChangeOpen}
    onclose={() => (emailChangeOpen = false)}
    {t}
  />
{/if}

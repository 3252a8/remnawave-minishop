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
  import Input from "$components/ui/input.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import { passkeysSupported, registerPasskey } from "$lib/webapp/passkeys.js";
  import type { Translate, UserProfile, VoidAction } from "$lib/webapp/types.js";
  import ProviderLogo from "../auth/ProviderLogo.svelte";

  type ExternalIdentity = {
    provider?: string;
    email?: string | null;
    display_name?: string | null;
  };
  type Passkey = {
    credential_id?: string;
    name?: string;
    created_at?: string | null;
    last_used_at?: string | null;
    backed_up?: boolean;
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
    goSettings: VoidAction;
    linkTelegramAccount: VoidAction;
    openLinkEmailDialog: VoidAction;
    openSetPasswordDialog: VoidAction;
    t: Translate;
    user?: UserProfile;
  };

  let {
    api,
    authProviders = [],
    brandTitle = "",
    goSettings,
    linkTelegramAccount,
    openLinkEmailDialog,
    openSetPasswordDialog,
    t,
    user = {},
  }: Props = $props();

  const externalIdentities = $derived((user.external_identities || []) as ExternalIdentity[]);
  const passkeys = $derived((user.passkeys || []) as Passkey[]);
  const emailAddresses = $derived((user.email_addresses || []) as AccountEmailAddress[]);
  const googleIdentity = $derived(externalIdentities.find((item) => item.provider === "google"));
  const yandexIdentity = $derived(externalIdentities.find((item) => item.provider === "yandex"));
  const passkeyEnabled = $derived(authProviders.includes("passkey"));
  const showPasskeys = $derived(passkeyEnabled || passkeys.length > 0);
  const googleVisible = $derived(authProviders.includes("google") || Boolean(googleIdentity));
  const yandexVisible = $derived(authProviders.includes("yandex") || Boolean(yandexIdentity));
  const emailEnabled = $derived(authProviders.includes("email") || Boolean(user.email));
  const telegramEnabled = $derived(
    authProviders.includes("telegram") || Boolean(user.telegram_linked)
  );
  let busy = $state(false);
  let status = $state("");
  let emailStep = $state<"idle" | "current" | "new" | "confirm">("idle");
  let currentCode = $state("");
  let newEmail = $state("");
  let newCode = $state("");
  let changeToken = $state("");
  let selectedNotificationEmail = $state("");

  $effect(() => {
    if (!selectedNotificationEmail) {
      selectedNotificationEmail = String(user.notification_email || user.email || "");
    }
  });

  function externalLabel(identity: ExternalIdentity | undefined): string {
    return String(identity?.email || identity?.display_name || "");
  }

  function linkExternal(provider: "google" | "yandex"): void {
    window.location.assign(`/auth/${provider}/start?purpose=link`);
  }

  function emailAddressSources(address: AccountEmailAddress): string {
    const labels = (address.sources || []).map((source) => {
      if (source === "google") return "Google";
      if (source === "yandex") return "Yandex";
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

  async function unlinkExternal(provider: "google" | "yandex"): Promise<void> {
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

  async function beginEmailChange(): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/email/change/current/request", {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!response.ok) throw response;
      currentCode = String(response.email_code || response.code || "");
      emailStep = "current";
    } catch {
      status = t("wa_auth_send_code_failed");
    } finally {
      busy = false;
    }
  }

  async function verifyCurrentEmail(): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/email/change/current/verify", {
        method: "POST",
        body: JSON.stringify({ code: currentCode }),
      });
      if (!response.ok) throw response;
      changeToken = String(response.change_token || "");
      emailStep = "new";
    } catch {
      status = t("wa_auth_invalid_code");
    } finally {
      busy = false;
    }
  }

  async function requestNewEmail(): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/email/change/new/request", {
        method: "POST",
        body: JSON.stringify({ email: newEmail, change_token: changeToken }),
      });
      if (!response.ok) throw response;
      newCode = String(response.email_code || response.code || "");
      emailStep = "confirm";
    } catch {
      status = t("wa_auth_send_code_failed");
    } finally {
      busy = false;
    }
  }

  async function confirmNewEmail(): Promise<void> {
    busy = true;
    status = "";
    try {
      const response = await api("/account/email/change/confirm", {
        method: "POST",
        body: JSON.stringify({ email: newEmail, code: newCode, change_token: changeToken }),
      });
      if (!response.ok) throw response;
      window.location.reload();
    } catch {
      status = t("wa_auth_invalid_code");
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
        <button
          class="settings-row attention-wrap"
          type="button"
          onclick={user.email ? beginEmailChange : openLinkEmailDialog}
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
          <div class="settings-row security-provider-row-linked">
            <ProviderLogo provider="google" size={21} />
            <span><strong>Google</strong><small>{externalLabel(googleIdentity)}</small></span>
            <button
              class="security-delete"
              type="button"
              aria-label={t("wa_security_unlink_provider", {}, "Unlink provider")}
              onclick={() => unlinkExternal("google")}
              disabled={busy}><Trash2 size={17} /></button
            >
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
          <div class="settings-row security-provider-row-linked">
            <ProviderLogo provider="yandex" size={21} />
            <span><strong>Yandex</strong><small>{externalLabel(yandexIdentity)}</small></span>
            <button
              class="security-delete"
              type="button"
              aria-label={t("wa_security_unlink_provider", {}, "Unlink provider")}
              onclick={() => unlinkExternal("yandex")}
              disabled={busy}><Trash2 size={17} /></button
            >
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
    </div>
  </Card>

  {#if emailAddresses.length}
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
              {#if !address.sources?.some((source) => source === "google" || source === "yandex")}
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

  {#if emailStep !== "idle"}
    <Card class="security-card security-email-change">
      <h2>{t("wa_security_change_email", {}, "Change email")}</h2>
      {#if emailStep === "current"}
        <p>
          {t(
            "wa_security_current_email_code",
            { email: user.email },
            "Enter the code sent to your current email"
          )}
        </p>
        <Input
          bind:value={currentCode}
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="000000"
        />
        <Button class="wide" onclick={verifyCurrentEmail} disabled={busy}>{t("wa_continue")}</Button
        >
      {:else if emailStep === "new"}
        <Input
          bind:value={newEmail}
          type="email"
          autocomplete="email"
          placeholder={t("wa_email_placeholder")}
        />
        <Button class="wide" onclick={requestNewEmail} disabled={busy}
          >{t("wa_send_code_email")}</Button
        >
      {:else}
        <p>
          {t(
            "wa_security_new_email_code",
            { email: newEmail },
            "Enter the code sent to the new email"
          )}
        </p>
        <Input
          bind:value={newCode}
          inputmode="numeric"
          autocomplete="one-time-code"
          placeholder="000000"
        />
        <Button class="wide" onclick={confirmNewEmail} disabled={busy}>{t("wa_apply")}</Button>
      {/if}
    </Card>
  {/if}

  {#if showPasskeys}
    <Card class="security-card">
      <div class="security-card-head">
        <div>
          <h2>{t("wa_security_passkeys", {}, "Passkeys")}</h2>
          <p>{t("wa_security_passkeys_hint", {}, "Sign in with biometrics or your device PIN")}</p>
        </div>
        {#if passkeyEnabled}<Button
            size="sm"
            onclick={addPasskey}
            disabled={busy || !passkeysSupported()}><Fingerprint size={16} />{t("wa_add")}</Button
          >{/if}
      </div>
      {#if passkeys.length}
        <div class="security-passkey-list">
          {#each passkeys as passkey (passkey.credential_id)}
            <div class="settings-row settings-row-linked">
              <Fingerprint size={21} />
              <span
                ><strong>{passkey.name || "Passkey"}</strong><small
                  >{passkey.backed_up
                    ? t("wa_security_passkey_synced", {}, "Synced")
                    : t("wa_security_passkey_device", {}, "This device")}</small
                ></span
              >
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

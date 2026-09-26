<script lang="ts">
  import type { LanguageOption } from "$lib/webapp/languageView.js";
  import {
    Check,
    ChevronsUpDown,
    Globe2,
    Fingerprint,
    LockKeyhole,
    Mail,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { Select, Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import EmailCodeScreen from "./EmailCodeScreen.svelte";
  import Input from "$components/ui/input.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { buildExternalOAuthStartUrl, shouldShowInviteOnlyHint } from "$lib/webapp/authHelpers.js";
  import { loginWithPasskey, passkeysSupported } from "$lib/webapp/passkeys.js";
  import ProviderLogo from "./ProviderLogo.svelte";

  type WebappConfig = Record<string, unknown> & {
    authProviders?: string[];
    compactLoginEnabled?: boolean;
    devMode?: boolean;
    emailAuthEnabled?: boolean;
    registrationInviteOnlyEnabled?: boolean;
    wideAuthProviders?: string[];
  };
  type Brand = Record<string, unknown>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Action = () => void | Promise<void>;

  const DEV_LOGIN_ACCOUNTS = [
    { email: "runes.admin@example.com", labelKey: "wa_dev_login_admin" },
    { email: "runes.active@example.com", labelKey: "wa_dev_login_active" },
    { email: "runes.expired@example.com", labelKey: "wa_dev_login_expired" },
  ] as const;
  const PROVIDER_ORDER = ["telegram", "email", "google", "yandex", "discord", "passkey"] as const;

  type Props = {
    authBusy?: boolean;
    authIsError?: boolean;
    authResendCooldown?: number;
    authStatus?: string;
    brand?: Brand;
    brandTitle?: string;
    CFG: WebappConfig;
    clearLoginEmailError: (event?: Event) => void;
    currentLang?: string;
    currentLanguageOption?: LanguageOption | null;
    email?: string;
    emailCode?: string;
    emailPassword?: string;
    languageClickGuard?: boolean;
    languageClickGuardArmed?: boolean;
    languageMenuOpen?: boolean;
    languageOptions?: LanguageOption[];
    loginEmailFieldError?: string;
    loginEmailTooltipOpen?: boolean;
    loginWithEmailPassword: Action;
    onBackToLogin: Action;
    openExternalLink: (url: string) => void;
    openTelegramLogin: Action;
    passwordLoginFallback?: boolean;
    passwordLoginMode?: boolean;
    pendingEmail?: string;
    privacyPolicyUrl?: string;
    requestEmailCode: Action;
    screen?: string;
    setLanguageMenuOpen?: (open: boolean) => void;
    setPasswordLoginMode: (enabled: boolean) => void;
    submitEmailOnEnter: (event: KeyboardEvent) => void;
    t: Translate;
    telegramLoginBusy?: boolean;
    telegramLoginChecking?: boolean;
    telegramLoginLabel?: string;
    telegramLoginUnavailable?: boolean;
    telegramLoginUnavailableMessage?: string;
    updateLoginLanguage?: (language: string) => void;
    userAgreementUrl?: string;
    verifyEmailCode: Action;
  };

  let {
    screen = "login",
    CFG,
    brand = {},
    brandTitle = "",
    email = $bindable(""),
    emailPassword = $bindable(""),
    emailCode = $bindable(""),
    pendingEmail = "",
    authStatus = "",
    authIsError = false,
    authBusy = false,
    authResendCooldown = 0,
    loginEmailFieldError = "",
    loginEmailTooltipOpen = false,
    passwordLoginFallback = false,
    passwordLoginMode = false,
    telegramLoginBusy = false,
    telegramLoginUnavailable = false,
    telegramLoginChecking = false,
    telegramLoginLabel = "",
    telegramLoginUnavailableMessage = "",
    privacyPolicyUrl = "",
    userAgreementUrl = "",
    currentLang = "ru",
    currentLanguageOption = null,
    languageOptions = [],
    languageMenuOpen = $bindable(false),
    languageClickGuard = false,
    languageClickGuardArmed = false,
    t,
    setLanguageMenuOpen = () => {},
    updateLoginLanguage = () => {},
    requestEmailCode,
    loginWithEmailPassword,
    verifyEmailCode,
    openTelegramLogin,
    openExternalLink,
    submitEmailOnEnter,
    onBackToLogin,
    clearLoginEmailError,
    setPasswordLoginMode,
  }: Props = $props();

  let authPanelHeight = $state(0);
  let externalLoginBusy = $state(false);
  let externalLoginStatus = $state("");
  let emailFormOpen = $state(false);

  const emailAuthEnabled = $derived(CFG.emailAuthEnabled !== false);
  const authProviders = $derived(
    Array.isArray(CFG.authProviders) ? CFG.authProviders : ["telegram"]
  );
  const compactLoginEnabled = $derived(
    CFG.compactLoginEnabled === true && authProviders.length > 1
  );
  const wideAuthProviders = $derived(
    Array.isArray(CFG.wideAuthProviders) ? CFG.wideAuthProviders : []
  );
  const compactEmail = $derived(isCompact("email"));
  const orderedProviders = $derived(
    PROVIDER_ORDER.filter((provider) =>
      provider === "email" ? emailAuthEnabled && compactEmail : authProviders.includes(provider)
    ).sort((left, right) => Number(isCompact(left)) - Number(isCompact(right)))
  );
  const showEmailForm = $derived(emailAuthEnabled && (!compactEmail || emailFormOpen));
  const passwordModeActive = $derived(Boolean(passwordLoginMode && emailAuthEnabled));
  const authCardHeight = $derived(authPanelHeight ? `${authPanelHeight}px` : undefined);
  const showLanguageSelect = $derived(languageOptions.length > 1);
  const showInviteOnlyHint = $derived(shouldShowInviteOnlyHint(CFG));
  const languageSelectContentProps = { trapFocus: false } as Record<string, unknown>;

  function isCompact(provider: string): boolean {
    return compactLoginEnabled && !wideAuthProviders.includes(provider);
  }

  function closeLanguageFromGuard(event: Event) {
    event.preventDefault();
    event.stopPropagation();
    if (languageClickGuardArmed) setLanguageMenuOpen(false);
  }

  function openProvider(provider: "discord" | "google" | "yandex"): void {
    const referral = new URLSearchParams(window.location.search).get("ref") || "";
    window.location.assign(buildExternalOAuthStartUrl(provider, "login", currentLang, referral));
  }

  async function openPasskeyLogin(): Promise<void> {
    externalLoginBusy = true;
    externalLoginStatus = "";
    try {
      await loginWithPasskey(String(CFG.apiBase || "/api"));
    } catch {
      externalLoginStatus = t("wa_security_passkey_failed", {}, "Could not sign in with passkey");
    } finally {
      externalLoginBusy = false;
    }
  }

  async function loginAsDevAccount(accountEmail: string): Promise<void> {
    email = accountEmail;
    emailCode = "";
    await requestEmailCode();
    await verifyEmailCode();
  }
</script>

{#if screen === "code"}
  <EmailCodeScreen
    bind:code={emailCode}
    email={pendingEmail}
    busy={authBusy}
    resendCooldown={authResendCooldown}
    status={authStatus}
    isError={authIsError}
    {t}
    onBack={onBackToLogin}
    onConfirm={verifyEmailCode}
    onResend={requestEmailCode}
  />
{:else}
  <div class="phone-screen auth-screen">
    <div class="auth-card-wrap">
      <div class="login-brand login-brand-auth">
        <BrandMark {brand} size="xl" />
        <h1>{brandTitle}</h1>
      </div>
      <section class="card auth-card" style:height={authCardHeight}>
        {#key passwordModeActive}
          <div
            class={`auth-mode-panel${passwordModeActive ? " auth-mode-panel-password" : ""}`}
            bind:clientHeight={authPanelHeight}
          >
            {#if passwordModeActive}
              <div class="auth-pane">
                <div class="auth-email-stack">
                  <div class="field-error-wrap">
                    <Tooltip.Root open={Boolean(loginEmailFieldError) && loginEmailTooltipOpen}>
                      <Input
                        bind:value={email}
                        type="email"
                        placeholder={t("wa_email_placeholder")}
                        autocomplete="email"
                        class={loginEmailFieldError ? "input-error" : ""}
                        oninput={clearLoginEmailError}
                      />
                      {#if loginEmailFieldError}
                        <Tooltip.Trigger
                          class="field-error-trigger"
                          aria-label={loginEmailFieldError}
                        >
                          <span class="field-error-icon" aria-hidden="true"
                            ><TriangleAlert size={18} /></span
                          >
                        </Tooltip.Trigger>
                      {/if}
                      {#if loginEmailFieldError}
                        <Tooltip.Portal>
                          <Tooltip.Content class="field-error-tooltip"
                            >{loginEmailFieldError}</Tooltip.Content
                          >
                        </Tooltip.Portal>
                      {/if}
                    </Tooltip.Root>
                  </div>
                  <Input
                    bind:value={emailPassword}
                    type="password"
                    placeholder={t("wa_password_placeholder")}
                    autocomplete="current-password"
                    onkeydown={(event) => {
                      if (event.key !== "Enter") return;
                      event.preventDefault();
                      loginWithEmailPassword();
                    }}
                  />
                  <Button class="wide" onclick={loginWithEmailPassword} disabled={authBusy}>
                    <LockKeyhole size={18} />
                    {t("wa_login_password_submit")}
                  </Button>
                  {#if passwordLoginFallback}
                    <button
                      class="link-button auth-code-fallback"
                      type="button"
                      onclick={requestEmailCode}
                      disabled={authBusy}
                    >
                      <Mail size={15} />
                      {t("wa_login_use_email_code")}
                    </button>
                  {:else}
                    <button
                      class="link-button auth-code-fallback"
                      type="button"
                      onclick={() => setPasswordLoginMode(false)}
                      disabled={authBusy}
                    >
                      {t("wa_login_other_method")}
                    </button>
                  {/if}
                </div>
              </div>
              {#if showInviteOnlyHint}
                <StatusMessage class="auth-login-status auth-invite-note">
                  {t("wa_auth_invite_only_hint")}
                </StatusMessage>
              {/if}
              {#if authStatus}
                <StatusMessage error={authIsError} class="auth-login-status">
                  {authStatus}
                </StatusMessage>
              {/if}
            {:else}
              {#if showEmailForm}
                <div class="auth-pane">
                  <div class="auth-email-stack">
                    <div class="field-error-wrap">
                      <Tooltip.Root open={Boolean(loginEmailFieldError) && loginEmailTooltipOpen}>
                        <Input
                          bind:value={email}
                          type="email"
                          placeholder={t("wa_email_placeholder")}
                          autocomplete="email"
                          class={loginEmailFieldError ? "input-error" : ""}
                          onkeydown={submitEmailOnEnter}
                          oninput={clearLoginEmailError}
                        />
                        {#if loginEmailFieldError}
                          <Tooltip.Trigger
                            class="field-error-trigger"
                            aria-label={loginEmailFieldError}
                          >
                            <span class="field-error-icon" aria-hidden="true"
                              ><TriangleAlert size={18} /></span
                            >
                          </Tooltip.Trigger>
                        {/if}
                        {#if loginEmailFieldError}
                          <Tooltip.Portal>
                            <Tooltip.Content class="field-error-tooltip"
                              >{loginEmailFieldError}</Tooltip.Content
                            >
                          </Tooltip.Portal>
                        {/if}
                      </Tooltip.Root>
                    </div>
                    <Button class="wide" onclick={requestEmailCode} disabled={authBusy}>
                      <Mail size={18} />
                      {t("wa_send_code_email")}
                    </Button>
                  </div>
                </div>
                {#if !compactEmail}
                  <div class="or-line"><span></span>{t("wa_or")}<span></span></div>
                {/if}
              {/if}
              <div class="auth-pane auth-provider-stack">
                {#each orderedProviders as provider (provider)}
                  {#if provider === "telegram"}
                    <Button
                      variant="secondary"
                      class={`${isCompact("telegram") ? "auth-provider-compact" : "wide"} auth-provider-button telegram-login-button${telegramLoginUnavailable ? " unavailable" : ""}${telegramLoginChecking ? " checking" : ""}`}
                      onclick={openTelegramLogin}
                      disabled={authBusy || telegramLoginBusy || telegramLoginUnavailable}
                      aria-label={telegramLoginLabel}
                      data-auth-provider="telegram"
                    >
                      {#if telegramLoginChecking}
                        <Spinner size="sm" />
                      {:else}
                        <ProviderLogo
                          provider="telegram"
                          size={isCompact("telegram") ? 26 : 18}
                          bare={isCompact("telegram")}
                        />
                      {/if}
                      {#if !isCompact("telegram")}{telegramLoginLabel}{/if}
                    </Button>
                  {/if}
                  {#if provider === "email"}
                    <Button
                      variant="secondary"
                      class="auth-provider-button auth-provider-compact"
                      onclick={() => (emailFormOpen = !emailFormOpen)}
                      disabled={authBusy}
                      aria-label={t("wa_send_code_email")}
                      aria-expanded={emailFormOpen}
                      data-auth-provider="email"
                    >
                      <Mail size={26} aria-hidden="true" />
                    </Button>
                  {/if}
                  {#if provider === "google"}
                    <Button
                      class={`${isCompact("google") ? "auth-provider-compact" : "wide"} auth-provider-button`}
                      variant="secondary"
                      onclick={() => openProvider("google")}
                      disabled={authBusy || externalLoginBusy}
                      aria-label={t("wa_login_google", {}, "Continue with Google")}
                      data-auth-provider="google"
                    >
                      <ProviderLogo provider="google" size={isCompact("google") ? 26 : 18} />
                      {#if !isCompact("google")}{t(
                          "wa_login_google",
                          {},
                          "Continue with Google"
                        )}{/if}
                    </Button>
                  {/if}
                  {#if provider === "yandex"}
                    <Button
                      class={`${isCompact("yandex") ? "auth-provider-compact" : "wide"} auth-provider-button`}
                      variant="secondary"
                      onclick={() => openProvider("yandex")}
                      disabled={authBusy || externalLoginBusy}
                      aria-label={t("wa_login_yandex", {}, "Continue with Yandex")}
                      data-auth-provider="yandex"
                    >
                      <ProviderLogo
                        provider="yandex"
                        size={isCompact("yandex") ? 38 : 18}
                        bare={isCompact("yandex")}
                      />
                      {#if !isCompact("yandex")}{t(
                          "wa_login_yandex",
                          {},
                          "Continue with Yandex"
                        )}{/if}
                    </Button>
                  {/if}
                  {#if provider === "discord"}
                    <Button
                      class={`${isCompact("discord") ? "auth-provider-compact" : "wide"} auth-provider-button`}
                      variant="secondary"
                      onclick={() => openProvider("discord")}
                      disabled={authBusy || externalLoginBusy}
                      aria-label={t("wa_login_discord", {}, "Continue with Discord")}
                      data-auth-provider="discord"
                    >
                      <ProviderLogo provider="discord" size={isCompact("discord") ? 26 : 18} />
                      {#if !isCompact("discord")}{t(
                          "wa_login_discord",
                          {},
                          "Continue with Discord"
                        )}{/if}
                    </Button>
                  {/if}
                  {#if provider === "passkey"}
                    <Button
                      class={`${isCompact("passkey") ? "auth-provider-compact" : "wide"} auth-provider-button`}
                      variant="secondary"
                      onclick={openPasskeyLogin}
                      disabled={authBusy || externalLoginBusy || !passkeysSupported()}
                      aria-label={t("wa_login_passkey", {}, "Sign in with passkey")}
                      data-auth-provider="passkey"
                    >
                      <Fingerprint
                        size={isCompact("passkey") ? 26 : 18}
                        data-provider-logo="passkey"
                      />
                      {#if !isCompact("passkey")}{t(
                          "wa_login_passkey",
                          {},
                          "Sign in with passkey"
                        )}{/if}
                    </Button>
                  {/if}
                {/each}
              </div>
              {#if emailAuthEnabled}
                <div class="password-switch-stack">
                  <div class="password-switch-divider" aria-hidden="true"></div>
                  <button
                    class="link-button password-switch-button"
                    type="button"
                    onclick={() => setPasswordLoginMode(true)}
                    disabled={authBusy}
                  >
                    <LockKeyhole size={15} />
                    {t("wa_login_use_password")}
                  </button>
                </div>
              {/if}
              {#if !telegramLoginChecking && (authStatus || telegramLoginUnavailableMessage || externalLoginStatus)}
                <StatusMessage
                  error={authIsError || Boolean(telegramLoginUnavailableMessage)}
                  class="auth-login-status"
                >
                  {authStatus || telegramLoginUnavailableMessage || externalLoginStatus}
                </StatusMessage>
              {:else if showInviteOnlyHint}
                <StatusMessage class="auth-login-status auth-invite-note">
                  {t("wa_auth_invite_only_hint")}
                </StatusMessage>
              {/if}
            {/if}
          </div>
        {/key}
      </section>
      {#if (import.meta.env.DEV || CFG.devMode === true) && emailAuthEnabled}
        <section class="dev-login-panel" aria-label={t("wa_dev_login_title")}>
          <div class="dev-login-heading">
            <span>{t("wa_dev_login_title")}</span>
            <small>{t("wa_dev_login_hint")}</small>
          </div>
          <div class="dev-login-actions">
            {#each DEV_LOGIN_ACCOUNTS as account (account.email)}
              <Button
                variant="secondary"
                class="dev-login-button"
                onclick={() => loginAsDevAccount(account.email)}
                disabled={authBusy}
              >
                <span>{t(account.labelKey)}</span>
                <small>{account.email}</small>
              </Button>
            {/each}
          </div>
        </section>
      {/if}
      {#if userAgreementUrl || privacyPolicyUrl || showLanguageSelect}
        <div class="auth-legal">
          {#if userAgreementUrl || privacyPolicyUrl}
            <span class="auth-legal-intro">{t("wa_auth_legal_intro")}</span>
            <div class="auth-legal-links">
              {#if privacyPolicyUrl}
                <a
                  href={privacyPolicyUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onclick={(e) => {
                    e.preventDefault();
                    openExternalLink(privacyPolicyUrl);
                  }}
                >
                  {t("wa_auth_legal_privacy")}
                </a>
              {/if}
              {#if privacyPolicyUrl && userAgreementUrl}
                <span>{t("wa_auth_legal_and")}</span>
              {/if}
              {#if userAgreementUrl}
                <a
                  href={userAgreementUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onclick={(e) => {
                    e.preventDefault();
                    openExternalLink(userAgreementUrl);
                  }}
                >
                  {t("wa_auth_legal_agreement")}
                </a>
              {/if}
            </div>
          {/if}
          {#if showLanguageSelect}
            {#if languageMenuOpen || languageClickGuard}
              <button
                class="language-select-guard"
                class:language-select-guard--armed={languageClickGuardArmed}
                type="button"
                aria-label={t("wa_close")}
                onpointerdown={closeLanguageFromGuard}
                onclick={closeLanguageFromGuard}
              ></button>
            {/if}
            <Select.Root
              type="single"
              bind:open={languageMenuOpen}
              value={currentLang}
              items={languageOptions}
              onOpenChange={setLanguageMenuOpen}
              onValueChange={updateLoginLanguage}
            >
              <Select.Trigger class="auth-language-trigger" aria-label={t("wa_settings_language")}>
                <Globe2 size={13} />
                <span class="emoji-flag" aria-hidden="true"
                  >{currentLanguageOption?.flag || "🏳️"}</span
                >
                <span>{currentLanguageOption?.label || currentLang}</span>
                <ChevronsUpDown size={12} />
              </Select.Trigger>
              <Select.Content
                class="language-select-content auth-language-content"
                side="bottom"
                align="center"
                sideOffset={7}
                {...languageSelectContentProps}
              >
                <Select.Viewport class="language-select-viewport">
                  {#each languageOptions as option (option.value)}
                    <Select.Item
                      value={option.value}
                      label={option.label}
                      class="language-select-item"
                    >
                      <span class="language-select-item-main">
                        <span class="emoji-flag" aria-hidden="true">{option.flag}</span>
                        <span>{option.label}</span>
                      </span>
                      <Check size={15} class="language-select-item-check" />
                    </Select.Item>
                  {/each}
                </Select.Viewport>
              </Select.Content>
            </Select.Root>
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

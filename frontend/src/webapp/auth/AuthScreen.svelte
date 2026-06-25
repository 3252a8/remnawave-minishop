<script>
  import {
    Check,
    ChevronsUpDown,
    Globe2,
    LockKeyhole,
    Mail,
    Send,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { Select, Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import EmailCodeScreen from "./EmailCodeScreen.svelte";
  import Input from "$components/ui/input.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";

  export let screen;
  export let CFG;
  export let brand = {};
  export let brandTitle;
  export let email;
  export let emailPassword;
  export let emailCode;
  export let pendingEmail;
  export let authStatus;
  export let authIsError;
  export let authBusy;
  export let authResendCooldown;
  export let loginEmailFieldError;
  export let loginEmailTooltipOpen;
  export let passwordLoginFallback;
  export let passwordLoginMode;
  export let telegramLoginBusy;
  export let telegramLoginUnavailable;
  export let telegramLoginChecking;
  export let telegramLoginLabel;
  export let telegramLoginUnavailableMessage;
  export let privacyPolicyUrl;
  export let userAgreementUrl;
  export let currentLang = "ru";
  /** @type {import("../../lib/webapp/languageView.js").LanguageOption | null} */
  export let currentLanguageOption = null;
  /** @type {import("../../lib/webapp/languageView.js").LanguageOption[]} */
  export let languageOptions = [];
  export let languageMenuOpen = false;
  export let languageClickGuard = false;
  export let languageClickGuardArmed = false;
  export let t;
  /** @type {(open: boolean) => void} */
  export let setLanguageMenuOpen = () => {};
  /** @type {(language: string) => void} */
  export let updateLoginLanguage = () => {};
  export let requestEmailCode;
  export let loginWithEmailPassword;
  export let verifyEmailCode;
  export let openTelegramLogin;
  export let openExternalLink;
  export let submitEmailOnEnter;
  export let onBackToLogin;
  export let clearLoginEmailError;
  export let setPasswordLoginMode;

  let authPanelHeight = 0;

  $: emailAuthEnabled = CFG.emailAuthEnabled !== false;
  $: passwordModeActive = Boolean(passwordLoginMode && emailAuthEnabled);
  $: authCardHeight = authPanelHeight ? `${authPanelHeight}px` : undefined;
  $: showLanguageSelect = languageOptions.length > 1;

  function closeLanguageFromGuard(event) {
    event.preventDefault();
    event.stopPropagation();
    if (languageClickGuardArmed) setLanguageMenuOpen(false);
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
                      {t("wa_login_use_email_code")}
                    </button>
                  {/if}
                </div>
              </div>
              {#if authStatus}
                <StatusMessage error={authIsError} class="auth-login-status">
                  {authStatus}
                </StatusMessage>
              {/if}
            {:else}
              {#if emailAuthEnabled}
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
                <div class="or-line"><span></span>{t("wa_or")}<span></span></div>
              {/if}
              <div class="auth-pane">
                <Button
                  variant="telegram"
                  class={`wide telegram-login-button${telegramLoginUnavailable ? " unavailable" : ""}${telegramLoginChecking ? " checking" : ""}`}
                  onclick={openTelegramLogin}
                  disabled={authBusy || telegramLoginBusy || telegramLoginUnavailable}
                  aria-label={telegramLoginLabel}
                >
                  <span class="telegram-login-text">
                    {#if telegramLoginChecking}
                      <Spinner size="sm" />
                    {:else}
                      <Send size={17} />
                    {/if}
                    {telegramLoginLabel}
                  </span>
                </Button>
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
              {#if !telegramLoginChecking && (authStatus || telegramLoginUnavailableMessage)}
                <StatusMessage
                  error={authIsError || Boolean(telegramLoginUnavailableMessage)}
                  class="auth-login-status"
                >
                  {authStatus || telegramLoginUnavailableMessage}
                </StatusMessage>
              {/if}
            {/if}
          </div>
        {/key}
      </section>
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
                trapFocus={false}
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

<script>
  import {
    ArrowLeft,
    LockKeyhole,
    Mail,
    RefreshCw,
    Send,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
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
  export let t;
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

  $: passwordModeActive = Boolean(passwordLoginMode && CFG.emailAuthEnabled !== false);
  $: authCardHeight = authPanelHeight ? `${authPanelHeight}px` : undefined;
</script>

<div class="phone-screen auth-screen">
  {#if screen === "code"}
    <header class="screen-head center-title">
      <Button variant="icon" size="icon" onclick={onBackToLogin} aria-label={t("wa_back")}>
        <ArrowLeft size={19} />
      </Button>
      <div>
        <h1>{t("wa_email_verification_title")}</h1>
        <p>{t("wa_email_sent_to", { email: pendingEmail })}</p>
      </div>
      <span></span>
    </header>
    <div class="otp-wrap">
      <label class="otp-input-wrap">
        <input
          bind:value={emailCode}
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          aria-label={t("wa_email_code_aria")}
        />
        <span class="otp-slots" aria-hidden="true">
          {#each Array.from({ length: 6 }) as _, index}
            <span class:filled={emailCode[index]}>{emailCode[index] || ""}</span>
          {/each}
        </span>
      </label>
      <Button class="wide" onclick={verifyEmailCode} disabled={authBusy}>
        {t("wa_confirm")}
      </Button>
      {#if authStatus}
        <StatusMessage error={authIsError}>{authStatus}</StatusMessage>
      {/if}
      <button
        class="link-button"
        type="button"
        onclick={requestEmailCode}
        disabled={authBusy || authResendCooldown > 0}
      >
        <RefreshCw size={15} />
        {authResendCooldown > 0
          ? t("wa_auth_resend_wait", { seconds: authResendCooldown })
          : t("wa_resend_code")}
      </button>
    </div>
  {:else}
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
                        on:input={clearLoginEmailError}
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
                    on:keydown={(event) => {
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
            {:else if CFG.emailAuthEnabled !== false}
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
                        on:keydown={submitEmailOnEnter}
                        on:input={clearLoginEmailError}
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
      {#if userAgreementUrl || privacyPolicyUrl}
        <div class="auth-legal">
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
        </div>
      {/if}
    </div>
  {/if}
</div>

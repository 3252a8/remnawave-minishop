<script>
  import { ArrowLeft, Mail, RefreshCw, Send, TriangleAlert } from "lucide-svelte";
  import { Tooltip } from "bits-ui";

  import Button from "../../lib/components/ui/button.svelte";
  import BrandMark from "../../BrandMark.svelte";
  import Card from "../../lib/components/ui/card.svelte";
  import Input from "../../lib/components/ui/input.svelte";

  export let screen;
  export let CFG;
  export let brandTitle;
  export let brandEmoji;
  export let email;
  export let emailCode;
  export let pendingEmail;
  export let authStatus;
  export let authIsError;
  export let authBusy;
  export let authResendCooldown;
  export let loginEmailFieldError;
  export let loginEmailTooltipOpen;
  export let telegramLoginBusy;
  export let telegramLoginUnavailable;
  export let telegramLoginChecking;
  export let telegramLoginLabel;
  export let telegramLoginUnavailableMessage;
  export let privacyPolicyUrl;
  export let userAgreementUrl;
  export let t;
  export let requestEmailCode;
  export let verifyEmailCode;
  export let openTelegramLogin;
  export let openExternalLink;
  export let submitEmailOnEnter;
  export let onBackToLogin;
  export let clearLoginEmailError;
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
        <div class:error={authIsError} class="status-line">{authStatus}</div>
      {/if}
      <button
        class="link-button"
        type="button"
        on:click={requestEmailCode}
        disabled={authBusy || authResendCooldown > 0}
      >
        <RefreshCw size={15} />
        {authResendCooldown > 0 ? t("wa_auth_resend_wait", { seconds: authResendCooldown }) : t("wa_resend_code")}
      </button>
    </div>
  {:else}
    <div class="auth-card-wrap">
      <div class="login-brand login-brand-auth">
        <BrandMark class="brand-mark-xl" logoUrl={CFG.logoUrl} emoji={brandEmoji} />
        <h1>{brandTitle}</h1>
      </div>
      <Card class="auth-card">
        {#if CFG.emailAuthEnabled !== false}
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
                    <Tooltip.Trigger class="field-error-trigger" aria-label={loginEmailFieldError}>
                      <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
                    </Tooltip.Trigger>
                  {/if}
                  {#if loginEmailFieldError}
                    <Tooltip.Portal>
                      <Tooltip.Content class="field-error-tooltip">{loginEmailFieldError}</Tooltip.Content>
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
        {/if}
        {#if CFG.emailAuthEnabled !== false}
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
                <span class="telegram-button-spinner" aria-hidden="true"></span>
              {:else}
                <Send size={17} />
              {/if}
              {telegramLoginLabel}
            </span>
          </Button>
        </div>
        {#if !telegramLoginChecking && (authStatus || telegramLoginUnavailableMessage)}
          <div
            class:error={authIsError || Boolean(telegramLoginUnavailableMessage)}
            class="status-line auth-login-status"
          >
            {authStatus || telegramLoginUnavailableMessage}
          </div>
        {/if}
      </Card>
      {#if userAgreementUrl || privacyPolicyUrl}
        <div class="auth-legal">
          <span class="auth-legal-intro">{t("wa_auth_legal_intro")}</span>
          <div class="auth-legal-links">
            {#if privacyPolicyUrl}
              <a
                href={privacyPolicyUrl}
                target="_blank"
                rel="noopener noreferrer"
                on:click|preventDefault={() => openExternalLink(privacyPolicyUrl)}
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
                on:click|preventDefault={() => openExternalLink(userAgreementUrl)}
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

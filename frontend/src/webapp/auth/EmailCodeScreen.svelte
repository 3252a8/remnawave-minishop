<script>
  import { ArrowLeft, RefreshCw } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";

  export let code = "";
  export let email = "";
  export let busy = false;
  export let resendCooldown = 0;
  export let status = "";
  export let isError = false;
  export let t = (key) => key;
  export let onBack = () => {};
  export let onConfirm = () => {};
  export let onResend = () => {};
</script>

<div class="phone-screen auth-screen">
  <header class="screen-head center-title">
    <Button variant="icon" size="icon" onclick={onBack} aria-label={t("wa_back")}>
      <ArrowLeft size={19} />
    </Button>
    <div>
      <h1>{t("wa_email_verification_title")}</h1>
      <p>{t("wa_email_sent_to", { email })}</p>
    </div>
    <span></span>
  </header>
  <div class="otp-wrap">
    <label class="otp-input-wrap">
      <input
        bind:value={code}
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        aria-label={t("wa_email_code_aria")}
      />
      <span class="otp-slots" aria-hidden="true">
        {#each Array.from({ length: 6 }) as _, index}
          <span class:filled={code[index]}>{code[index] || ""}</span>
        {/each}
      </span>
    </label>
    <Button class="wide" onclick={onConfirm} disabled={busy}>
      {t("wa_confirm")}
    </Button>
    {#if status}
      <StatusMessage error={isError}>{status}</StatusMessage>
    {/if}
    <button
      class="link-button"
      type="button"
      onclick={onResend}
      disabled={busy || resendCooldown > 0}
    >
      <RefreshCw size={15} />
      {resendCooldown > 0
        ? t("wa_auth_resend_wait", { seconds: resendCooldown })
        : t("wa_resend_code")}
    </button>
  </div>
</div>

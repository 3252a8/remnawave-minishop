<script lang="ts">
  import { ArrowLeft, RefreshCw } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import EmailOtpInput from "./EmailOtpInput.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Action = () => void | Promise<void>;

  type Props = {
    busy?: boolean;
    code?: string;
    email?: string;
    embedded?: boolean;
    isError?: boolean;
    onBack?: Action;
    onConfirm?: Action;
    onResend?: Action;
    resendCooldown?: number;
    status?: string;
    t?: Translate;
  };

  let {
    code = $bindable(""),
    email = "",
    embedded = false,
    busy = false,
    resendCooldown = 0,
    status = "",
    isError = false,
    t = (key) => key,
    onBack = () => {},
    onConfirm = () => {},
    onResend = () => {},
  }: Props = $props();

  let submitting = $state(false);

  async function submitCode(): Promise<void> {
    if (busy || submitting || code.length !== 6) return;
    submitting = true;
    try {
      await onConfirm();
    } finally {
      submitting = false;
    }
  }

  function handleCodeInput(): void {
    if (code.length === 6) void submitCode();
  }

  function handleSubmit(event: SubmitEvent): void {
    event.preventDefault();
    void submitCode();
  }
</script>

<div class="phone-screen auth-screen" class:embedded>
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
  <form class="otp-wrap" onsubmit={handleSubmit}>
    <EmailOtpInput
      bind:code
      ariaLabel={t("wa_email_code_aria")}
      disabled={busy || submitting}
      oninput={handleCodeInput}
    />
    <Button class="wide" type="submit" disabled={busy || submitting || code.length !== 6}>
      {t("wa_confirm")}
    </Button>
    {#if status}
      <StatusMessage error={isError}>{status}</StatusMessage>
    {/if}
    <button
      class="link-button"
      type="button"
      onclick={onResend}
      disabled={busy || submitting || resendCooldown > 0}
    >
      <RefreshCw size={15} />
      {resendCooldown > 0
        ? t("wa_auth_resend_wait", { seconds: resendCooldown })
        : t("wa_resend_code")}
    </button>
  </form>
</div>

<style>
  .phone-screen.auth-screen.embedded {
    box-sizing: border-box;
    width: 100%;
    min-height: 0;
    margin: 0;
    overflow: visible;
    padding: 0;
    background: transparent;
    align-content: start;
  }

  .embedded .screen-head {
    margin-bottom: 24px;
  }

  .embedded .screen-head h1 {
    font-size: clamp(24px, 3vw, 30px);
  }

  .embedded .screen-head p {
    margin-top: 8px;
    font-size: 14px;
    line-height: 1.45;
  }

  .embedded .otp-wrap {
    min-height: 0;
    align-content: start;
  }
</style>

<script lang="ts">
  import { onDestroy } from "svelte";
  import { ArrowLeft, CheckCircle2, Mail, RefreshCw } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { createCooldownTimer, emailError } from "$lib/webapp/authHelpers.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";
  import EmailOtpInput from "../auth/EmailOtpInput.svelte";

  type Step = "sending-current" | "current-code" | "new-email" | "new-code" | "success";
  type ErrorLike = { error?: string; retry_after?: number } | null;

  type Props = {
    api: ApiClient["api"];
    currentEmail: string;
    onclose?: VoidAction;
    open?: boolean;
    t: Translate;
  };

  let { api, currentEmail, onclose = () => {}, open = false, t }: Props = $props();
  let step = $state<Step>("sending-current");
  let currentCode = $state("");
  let newEmail = $state("");
  let newCode = $state("");
  let changeToken = $state("");
  let busy = $state(false);
  let status = $state("");
  let isError = $state(false);
  let resendCooldown = $state(0);
  let openHandled = $state(false);
  let generation = 0;

  const cooldownTimer = createCooldownTimer();
  const unsubscribeCooldown = cooldownTimer.subscribe((value) => (resendCooldown = value));
  onDestroy(() => {
    unsubscribeCooldown();
    cooldownTimer.clear();
  });

  function errorCode(error: unknown): string {
    const record = error && typeof error === "object" ? (error as ErrorLike) : null;
    return String(record?.error || "");
  }

  function flowError(error: unknown, fallback: string): string {
    const code = errorCode(error);
    if (code === "email_change_disabled") return t("wa_security_email_change_disabled");
    if (code === "email_auth_not_configured") return t("wa_security_email_change_unavailable");
    if (code === "email_not_linked") return t("wa_security_email_not_linked");
    if (code === "email_unchanged") return t("wa_security_email_unchanged");
    if (code === "email_already_in_use") return t("wa_security_email_already_in_use");
    if (code === "invalid_change_token") return t("wa_security_email_change_expired");
    if (code === "email_send_failed") return t("wa_auth_send_code_failed");
    if (code === "access_denied") return t("wa_auth_access_denied");
    return emailError(error, fallback, t);
  }

  function reset(): void {
    generation += 1;
    step = "sending-current";
    currentCode = "";
    newEmail = "";
    newCode = "";
    changeToken = "";
    busy = false;
    status = "";
    isError = false;
    cooldownTimer.clear();
    resendCooldown = 0;
  }

  function setError(error: unknown, fallback: string): void {
    status = flowError(error, fallback);
    isError = true;
  }

  function presetCode(response: Record<string, unknown>): string {
    return String(response.email_code || response.code || "")
      .replace(/\D/g, "")
      .slice(0, 6);
  }

  async function requestCurrentCode(): Promise<void> {
    const requestGeneration = generation;
    busy = true;
    status = "";
    isError = false;
    step = "sending-current";
    try {
      const response = unwrap(
        await api("/account/email/change/current/request", {
          method: "POST",
          body: JSON.stringify({}),
        })
      );
      if (!open || generation !== requestGeneration) return;
      currentCode = presetCode(response);
      step = "current-code";
      cooldownTimer.start(60);
    } catch (error: unknown) {
      if (!open || generation !== requestGeneration) return;
      step = "current-code";
      setError(error, t("wa_auth_send_code_failed"));
    } finally {
      if (open && generation === requestGeneration) busy = false;
    }
  }

  async function verifyCurrentEmail(): Promise<void> {
    if (currentCode.length !== 6) {
      setError({ error: "invalid_code" }, t("wa_auth_invalid_code"));
      return;
    }
    busy = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/email/change/current/verify", {
          method: "POST",
          body: JSON.stringify({ code: currentCode }),
        })
      );
      changeToken = String(response.change_token || "");
      if (!changeToken) throw { error: "invalid_change_token" };
      step = "new-email";
      cooldownTimer.clear();
    } catch (error: unknown) {
      setError(error, t("wa_auth_invalid_code"));
    } finally {
      busy = false;
    }
  }

  async function requestNewEmail(): Promise<void> {
    const normalized = newEmail.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
      setError({ error: "invalid_email" }, t("wa_auth_invalid_email"));
      return;
    }
    if (normalized === currentEmail.trim().toLowerCase()) {
      setError({ error: "email_unchanged" }, t("wa_security_email_unchanged"));
      return;
    }
    busy = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/email/change/new/request", {
          method: "POST",
          body: JSON.stringify({ email: normalized, change_token: changeToken }),
        })
      );
      newEmail = normalized;
      newCode = presetCode(response);
      step = "new-code";
      cooldownTimer.start(60);
    } catch (error: unknown) {
      setError(error, t("wa_auth_send_code_failed"));
    } finally {
      busy = false;
    }
  }

  async function confirmNewEmail(): Promise<void> {
    if (newCode.length !== 6) {
      setError({ error: "invalid_code" }, t("wa_auth_invalid_code"));
      return;
    }
    busy = true;
    status = "";
    isError = false;
    try {
      unwrap(
        await api("/account/email/change/confirm", {
          method: "POST",
          body: JSON.stringify({
            email: newEmail,
            code: newCode,
            change_token: changeToken,
          }),
        })
      );
      step = "success";
      cooldownTimer.clear();
    } catch (error: unknown) {
      setError(error, t("wa_auth_invalid_code"));
    } finally {
      busy = false;
    }
  }

  function resend(): void {
    if (resendCooldown > 0 || busy) return;
    if (step === "current-code") void requestCurrentCode();
    else if (step === "new-code") void requestNewEmail();
  }

  function editNewEmail(): void {
    if (busy) return;
    newCode = "";
    status = "";
    isError = false;
    step = "new-email";
  }

  function closeDialog(): void {
    const completed = step === "success";
    reset();
    openHandled = false;
    onclose();
    if (completed) window.location.reload();
  }

  $effect(() => {
    if (open && !openHandled) {
      openHandled = true;
      reset();
      void requestCurrentCode();
    } else if (!open && openHandled) {
      openHandled = false;
      reset();
    }
  });

  function dialogTitle(): string {
    if (step === "new-email") return t("wa_security_new_email_title");
    if (step === "new-code") return t("wa_security_confirm_new_email_title");
    if (step === "success") return t("wa_security_email_changed_title");
    return t("wa_security_change_email");
  }

  function dialogDescription(): string {
    if (step === "new-email") return t("wa_security_new_email_hint");
    if (step === "new-code") return t("wa_security_new_email_code", { email: newEmail });
    if (step === "success") return t("wa_security_email_changed_hint", { email: newEmail });
    return t("wa_security_current_email_code", { email: currentEmail });
  }
</script>

<Dialog
  {open}
  title={dialogTitle()}
  description={dialogDescription()}
  closeLabel={t("wa_close")}
  onclose={closeDialog}
  class="change-email-dialog"
>
  <div class="change-email-body">
    {#if step !== "success"}
      <span class="change-email-step">
        {t("wa_security_email_change_step", {
          current: step === "new-email" ? 2 : step === "new-code" ? 3 : 1,
          total: 3,
        })}
      </span>
    {/if}

    {#if step === "sending-current"}
      <div class="change-email-loading" role="status">
        <Spinner size="lg" />
        <span>{t("wa_security_sending_current_email_code", { email: currentEmail })}</span>
      </div>
    {:else if step === "current-code"}
      <form
        class="change-email-form"
        onsubmit={(event) => {
          event.preventDefault();
          void verifyCurrentEmail();
        }}
      >
        <EmailOtpInput
          bind:code={currentCode}
          ariaLabel={t("wa_email_code_aria")}
          disabled={busy}
          oninput={() => (status = "")}
        />
        <Button class="wide" type="submit" disabled={busy || currentCode.length !== 6}>
          {t("wa_continue")}
        </Button>
      </form>
      <button
        class="link-button"
        type="button"
        onclick={resend}
        disabled={busy || resendCooldown > 0}
      >
        <RefreshCw size={15} />
        {resendCooldown > 0
          ? t("wa_auth_resend_wait", { seconds: resendCooldown })
          : t("wa_resend_code")}
      </button>
    {:else if step === "new-email"}
      <form
        class="change-email-form"
        onsubmit={(event) => {
          event.preventDefault();
          void requestNewEmail();
        }}
      >
        <label class="change-email-field">
          <span>{t("wa_security_new_email_label")}</span>
          <Input
            bind:value={newEmail}
            type="email"
            autocomplete="email"
            placeholder={t("wa_email_placeholder")}
            disabled={busy}
            oninput={() => (status = "")}
          />
        </label>
        <Button class="wide" type="submit" disabled={busy || !newEmail.trim()}>
          <Mail size={17} />{t("wa_send_code_email")}
        </Button>
      </form>
    {:else if step === "new-code"}
      <button class="change-email-back" type="button" onclick={editNewEmail} disabled={busy}>
        <ArrowLeft size={16} />{t("wa_security_edit_new_email")}
      </button>
      <form
        class="change-email-form"
        onsubmit={(event) => {
          event.preventDefault();
          void confirmNewEmail();
        }}
      >
        <EmailOtpInput
          bind:code={newCode}
          ariaLabel={t("wa_email_code_aria")}
          disabled={busy}
          oninput={() => (status = "")}
        />
        <Button class="wide" type="submit" disabled={busy || newCode.length !== 6}>
          {t("wa_apply")}
        </Button>
      </form>
      <button
        class="link-button"
        type="button"
        onclick={resend}
        disabled={busy || resendCooldown > 0}
      >
        <RefreshCw size={15} />
        {resendCooldown > 0
          ? t("wa_auth_resend_wait", { seconds: resendCooldown })
          : t("wa_resend_code")}
      </button>
    {:else}
      <div class="change-email-success" role="status">
        <span><CheckCircle2 size={32} /></span>
        <strong>{newEmail}</strong>
        <p>{t("wa_security_email_changed_notice")}</p>
      </div>
      <Button class="wide" onclick={closeDialog}>{t("wa_done")}</Button>
    {/if}

    {#if status}
      <StatusMessage error={isError}>{status}</StatusMessage>
    {/if}
  </div>
</Dialog>

<style>
  .change-email-body,
  .change-email-form,
  .change-email-field,
  .change-email-success {
    display: grid;
  }

  .change-email-body {
    gap: 16px;
    padding: 18px;
  }

  .change-email-form {
    gap: 16px;
  }

  .change-email-field {
    gap: 7px;
  }

  .change-email-field > span {
    font-size: 13px;
    font-weight: 750;
  }

  .change-email-step {
    width: max-content;
    padding: 5px 9px;
    border-radius: 999px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 11%, transparent);
    font-size: 11px;
    font-weight: 800;
  }

  .change-email-loading {
    display: grid;
    min-height: 160px;
    place-items: center;
    align-content: center;
    gap: 14px;
    color: var(--muted);
    text-align: center;
    font-size: 13px;
    line-height: 1.45;
  }

  .change-email-back {
    width: max-content;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border: 0;
    padding: 0;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  .change-email-success {
    justify-items: center;
    gap: 10px;
    padding: 18px 4px 10px;
    text-align: center;
  }

  .change-email-success > span {
    width: 58px;
    height: 58px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    color: var(--success);
    background: color-mix(in srgb, var(--success) 13%, transparent);
  }

  .change-email-success strong {
    overflow-wrap: anywhere;
  }

  .change-email-success p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.45;
  }

  :global(.change-email-dialog) {
    width: min(100%, 460px);
  }

  :global(.change-email-dialog .otp-slots) {
    gap: 7px;
  }

  :global(.change-email-dialog .otp-slots span) {
    border-radius: var(--radius-inner);
    font-size: clamp(20px, 6vw, 25px);
  }
</style>

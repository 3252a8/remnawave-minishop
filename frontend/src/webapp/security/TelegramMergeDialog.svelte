<script lang="ts">
  import { onDestroy } from "svelte";
  import { CheckCircle2, RefreshCw } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { createCooldownTimer, emailError } from "$lib/webapp/authHelpers.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";
  import EmailOtpInput from "../auth/EmailOtpInput.svelte";

  type Props = {
    api: ApiClient["api"];
    email: string;
    open?: boolean;
    onclose: VoidAction;
    onmerged: (response: unknown) => Promise<void>;
    t: Translate;
  };

  let { api, email, open = false, onclose, onmerged, t }: Props = $props();
  let code = $state("");
  let busy = $state(false);
  let sending = $state(false);
  let success = $state(false);
  let status = $state("");
  let isError = $state(false);
  let resendCooldown = $state(0);
  let openHandled = $state(false);
  let generation = 0;

  const cooldown = createCooldownTimer();
  const unsubscribe = cooldown.subscribe((value) => (resendCooldown = value));
  onDestroy(() => {
    unsubscribe();
    cooldown.clear();
  });

  function errorMessage(error: unknown, fallback: string): string {
    const record = error && typeof error === "object" ? (error as Record<string, unknown>) : {};
    const code = String(record.error || "");
    if (code === "verified_email_required") return t("wa_telegram_merge_verified_email_required");
    if (
      [
        "account_merge_conflict",
        "account_merge_duplicate_promo_conflict",
        "account_merge_recurring_cancel_failed",
        "account_merge_google_conflict",
        "account_merge_yandex_conflict",
        "account_merge_provider_conflict",
        "account_merge_telegram_conflict",
        "account_merge_privileged_source",
        "account_merge_not_required",
        "account_merge_failed",
      ].includes(code)
    )
      return t(code);
    return emailError(error, fallback, t);
  }

  function reset(): void {
    generation += 1;
    code = "";
    busy = false;
    sending = false;
    success = false;
    status = "";
    isError = false;
    cooldown.clear();
  }

  async function requestCode(): Promise<void> {
    if (!open || busy || resendCooldown > 0) return;
    const requestGeneration = generation;
    busy = true;
    sending = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/telegram/merge/request", {
          method: "POST",
          body: JSON.stringify({}),
        })
      );
      if (!open || generation !== requestGeneration) return;
      const value = response as Record<string, unknown>;
      code = String(value.email_code || value.code || "")
        .replace(/\D/g, "")
        .slice(0, 6);
      status = t("wa_telegram_merge_code_sent", { email });
      cooldown.start(60);
    } catch (error: unknown) {
      if (!open || generation !== requestGeneration) return;
      status = errorMessage(error, t("wa_auth_send_code_failed"));
      isError = true;
    } finally {
      if (open && generation === requestGeneration) {
        busy = false;
        sending = false;
      }
    }
  }

  async function confirm(): Promise<void> {
    if (busy || code.length !== 6) return;
    busy = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/telegram/merge/confirm", {
          method: "POST",
          body: JSON.stringify({ email_code: code }),
        })
      );
      success = true;
      cooldown.clear();
      try {
        await onmerged(response);
      } catch {
        window.location.reload();
      }
    } catch (error: unknown) {
      status = errorMessage(error, t("wa_telegram_merge_failed"));
      isError = true;
    } finally {
      busy = false;
    }
  }

  function closeDialog(): void {
    if (busy) return;
    reset();
    openHandled = false;
    onclose();
  }

  $effect(() => {
    if (open && !openHandled) {
      openHandled = true;
      reset();
      void requestCode();
    } else if (!open && openHandled) {
      openHandled = false;
      reset();
    }
  });
</script>

<Dialog
  {open}
  title={t("wa_telegram_merge_title")}
  description={t("wa_telegram_merge_hint")}
  closeLabel={t("wa_close")}
  onclose={closeDialog}
  class="telegram-merge-dialog"
>
  <div class="telegram-merge-body">
    {#if success}
      <div class="telegram-merge-success" role="status">
        <CheckCircle2 size={36} />
        <strong>{t("wa_telegram_merge_done")}</strong>
      </div>
      <Button class="wide" onclick={closeDialog}>{t("wa_done")}</Button>
    {:else if sending}
      <div class="telegram-merge-loading" role="status">
        <Spinner size="lg" />
        <span>{t("wa_telegram_merge_sending")}</span>
      </div>
    {:else}
      <form
        class="telegram-merge-form"
        onsubmit={(event) => {
          event.preventDefault();
          void confirm();
        }}
      >
        <EmailOtpInput
          bind:code
          ariaLabel={t("wa_email_code_aria")}
          disabled={busy}
          oninput={() => (status = "")}
        />
        <Button class="wide" type="submit" disabled={busy || code.length !== 6}>
          {t("wa_telegram_merge_confirm")}
        </Button>
      </form>
      <button
        class="link-button telegram-merge-resend"
        type="button"
        onclick={() => void requestCode()}
        disabled={busy || resendCooldown > 0}
      >
        <RefreshCw size={15} />
        {resendCooldown > 0
          ? t("wa_auth_resend_wait", { seconds: resendCooldown })
          : t("wa_resend_code")}
      </button>
    {/if}
    {#if status && !success}
      <StatusMessage error={isError}>{status}</StatusMessage>
    {/if}
  </div>
</Dialog>

<style>
  .telegram-merge-body,
  .telegram-merge-form,
  .telegram-merge-loading,
  .telegram-merge-success {
    display: grid;
  }

  .telegram-merge-body,
  .telegram-merge-form {
    gap: 16px;
  }

  .telegram-merge-body {
    padding: 18px;
  }

  .telegram-merge-loading,
  .telegram-merge-success {
    min-height: 145px;
    place-items: center;
    align-content: center;
    gap: 12px;
    text-align: center;
  }

  .telegram-merge-loading {
    color: var(--muted);
  }

  .telegram-merge-success {
    color: var(--accent);
  }

  .telegram-merge-resend {
    width: max-content;
    max-width: 100%;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
</style>

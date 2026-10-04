<script lang="ts">
  import { onDestroy } from "svelte";
  import { CheckCircle2, RefreshCw } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import {
    accountMergeErrorMessage,
    authProviderName,
    buildExternalOAuthStartUrl,
    createCooldownTimer,
    emailError,
  } from "$lib/webapp/authHelpers.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import { confirmAccountMergeWithPasskey } from "$lib/webapp/passkeys.js";
  import type { Translate, VoidAction } from "$lib/webapp/types.js";
  import EmailOtpInput from "../auth/EmailOtpInput.svelte";

  type Props = {
    api: ApiClient["api"];
    currentLang?: string;
    open?: boolean;
    onclose: VoidAction;
    onmerged: (response: unknown) => Promise<void>;
    t: Translate;
  };

  let { api, currentLang = "ru", open = false, onclose, onmerged, t }: Props = $props();
  let code = $state("");
  let busy = $state(false);
  let loading = $state(false);
  let loaded = $state(false);
  let success = $state(false);
  let status = $state("");
  let isError = $state(false);
  let resendCooldown = $state(0);
  let openHandled = $state(false);
  let providers = $state<string[]>([]);
  let sourceProvider = $state("");
  let email = $state("");
  let emailAvailable = $state(false);
  let targetConfirmed = $state(false);
  let generation = 0;

  const cooldown = createCooldownTimer();
  const unsubscribe = cooldown.subscribe((value) => (resendCooldown = value));
  onDestroy(() => {
    unsubscribe();
    cooldown.clear();
  });

  function errorMessage(error: unknown, fallback: string): string {
    const record = error && typeof error === "object" ? (error as Record<string, unknown>) : {};
    const errorCode = String(record.error || "");
    if (errorCode === "verified_email_required") return t("wa_account_merge_email_unavailable");
    if (errorCode === "provider_conflict" || errorCode.startsWith("account_merge_"))
      return accountMergeErrorMessage(errorCode, t);
    return emailError(error, fallback, t);
  }

  function reset(): void {
    generation += 1;
    code = "";
    busy = false;
    loading = false;
    loaded = false;
    success = false;
    status = "";
    isError = false;
    providers = [];
    sourceProvider = "";
    email = "";
    emailAvailable = false;
    targetConfirmed = false;
    cooldown.clear();
    resendCooldown = 0;
  }

  async function requestCode(): Promise<void> {
    if (!open || busy || !emailAvailable || resendCooldown > 0) return;
    const requestGeneration = generation;
    busy = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/merge/request", { method: "POST", body: JSON.stringify({}) })
      );
      if (!open || generation !== requestGeneration) return;
      code = String(response.email_code || "")
        .replace(/\D/g, "")
        .slice(0, 6);
      status = t("wa_account_merge_code_sent", { email });
      cooldown.start(60);
    } catch (error: unknown) {
      if (!open || generation !== requestGeneration) return;
      status = errorMessage(error, t("wa_auth_send_code_failed"));
      isError = true;
    } finally {
      if (open && generation === requestGeneration) busy = false;
    }
  }

  async function loadStatus(): Promise<void> {
    const requestGeneration = generation;
    loading = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(await api("/account/merge/status"));
      if (!open || generation !== requestGeneration) return;
      providers = response.providers;
      sourceProvider = response.provider;
      email = response.email || "";
      emailAvailable = response.email_available;
      targetConfirmed = response.target_confirmed;
      loaded = true;
      if (emailAvailable && !targetConfirmed) await requestCode();
    } catch (error: unknown) {
      if (!open || generation !== requestGeneration) return;
      status = errorMessage(error, t("wa_account_merge_failed"));
      isError = true;
    } finally {
      if (open && generation === requestGeneration) loading = false;
    }
  }

  async function confirm(): Promise<void> {
    if (busy || !loaded || (!targetConfirmed && code.length !== 6)) return;
    busy = true;
    status = "";
    isError = false;
    try {
      const response = unwrap(
        await api("/account/merge/confirm", {
          method: "POST",
          body: JSON.stringify(targetConfirmed ? {} : { email_code: code }),
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
      if (
        error &&
        typeof error === "object" &&
        "error" in error &&
        error.error === "account_merge_confirmation_required"
      )
        targetConfirmed = false;
      status = errorMessage(error, t("wa_account_merge_failed"));
      isError = true;
    } finally {
      busy = false;
    }
  }

  async function reauthenticate(provider: string): Promise<void> {
    if (busy) return;
    if (provider !== "passkey") {
      busy = true;
      window.location.assign(buildExternalOAuthStartUrl(provider, "merge", currentLang));
      return;
    }
    busy = true;
    status = "";
    isError = false;
    try {
      await confirmAccountMergeWithPasskey(api);
      await loadStatus();
    } catch (error) {
      status = errorMessage(error, t("wa_security_passkey_failed"));
      isError = true;
    } finally {
      busy = false;
    }
  }

  async function closeDialog(): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      if (!success)
        unwrap(await api("/account/merge/cancel", { method: "POST", body: JSON.stringify({}) }));
      reset();
      openHandled = false;
      onclose();
    } catch (error: unknown) {
      status = errorMessage(error, t("wa_account_merge_failed"));
      isError = true;
      busy = false;
    }
  }

  $effect(() => {
    if (open && !openHandled) {
      openHandled = true;
      reset();
      void loadStatus();
    } else if (!open && openHandled) {
      openHandled = false;
      reset();
    }
  });
</script>

<Dialog
  {open}
  title={t("wa_account_merge_title")}
  description={t("wa_account_merge_hint")}
  closeLabel={t("wa_close")}
  onclose={() => void closeDialog()}
  class="account-merge-dialog"
>
  <div class="account-merge-body">
    {#if success}
      <div class="account-merge-result" role="status">
        <CheckCircle2 size={36} />
        <strong>{t("wa_account_merge_done")}</strong>
      </div>
      <Button class="wide" onclick={() => void closeDialog()}>{t("wa_done")}</Button>
    {:else if loading}
      <div class="account-merge-loading" role="status">
        <Spinner size="lg" />
        <span>{t("wa_account_merge_loading")}</span>
      </div>
    {:else if loaded}
      <p class="account-merge-source">
        {t("wa_account_merge_source", { provider: authProviderName(sourceProvider, t) })}
      </p>
      {#if targetConfirmed}
        <StatusMessage>{t("wa_account_merge_confirmed")}</StatusMessage>
        <Button class="wide" onclick={() => void confirm()} disabled={busy}>
          {t("wa_account_merge_confirm")}
        </Button>
      {:else}
        {#if providers.length}
          <div class="account-merge-providers">
            <p>{t("wa_account_merge_reauth_hint")}</p>
            {#each providers as provider (provider)}
              <Button
                class="wide"
                variant="secondary"
                disabled={busy}
                onclick={() => void reauthenticate(provider)}
              >
                {t("wa_account_merge_reauth", { provider: authProviderName(provider, t) })}
              </Button>
            {/each}
          </div>
        {/if}
        {#if emailAvailable}
          <form
            class="account-merge-form"
            onsubmit={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            <p>{t("wa_account_merge_email_hint", { email })}</p>
            <EmailOtpInput
              bind:code
              ariaLabel={t("wa_email_code_aria")}
              disabled={busy}
              oninput={() => (status = "")}
            />
            <Button class="wide" type="submit" disabled={busy || code.length !== 6}>
              {t("wa_account_merge_confirm")}
            </Button>
          </form>
          <Button
            variant="ghost"
            onclick={() => void requestCode()}
            disabled={busy || resendCooldown > 0}
          >
            <RefreshCw size={15} />
            {resendCooldown > 0
              ? t("wa_auth_resend_wait", { seconds: resendCooldown })
              : t("wa_resend_code")}
          </Button>
        {:else if !providers.length}
          <StatusMessage error>{t("wa_account_merge_unavailable")}</StatusMessage>
        {/if}
      {/if}
    {:else}
      <Button class="wide" onclick={() => void loadStatus()} disabled={busy}>
        {t("wa_retry")}
      </Button>
    {/if}
    {#if status && !success}
      <StatusMessage error={isError}>{status}</StatusMessage>
    {/if}
  </div>
</Dialog>

<style>
  .account-merge-body,
  .account-merge-form,
  .account-merge-providers,
  .account-merge-loading,
  .account-merge-result {
    display: grid;
    gap: 12px;
  }

  .account-merge-body {
    gap: 18px;
    padding: 18px;
  }

  .account-merge-body p {
    margin: 0;
    color: var(--muted);
    overflow-wrap: anywhere;
  }

  .account-merge-loading,
  .account-merge-result {
    min-height: 145px;
    place-items: center;
    align-content: center;
    text-align: center;
  }

  .account-merge-loading {
    color: var(--muted);
  }

  .account-merge-result {
    color: var(--accent);
  }
</style>

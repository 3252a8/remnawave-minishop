<script lang="ts">
  /**
   * The signed-in side of QR sign-in: show which device is asking, then require
   * the number from that device's screen. Somebody who was merely sent a code has
   * no screen to read it from, and three wrong numbers decline the request.
   */
  import { untrack } from "svelte";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Props = {
    open?: boolean;
    code?: string;
    api: ApiClient["api"];
    t: Translate;
    onclose: () => void;
  };
  type Stage = "loading" | "confirm" | "approved" | "declined" | "failed";
  type Failure = { error?: string; attempts_left?: number } | null;

  let { open = false, code = "", api, t, onclose }: Props = $props();

  let stage = $state<Stage>("loading");
  let busy = $state(false);
  let requestId = $state("");
  let device = $state("");
  let ip = $state("");
  let number = $state("");
  let message = $state("");

  function failureMessage(error: unknown): string {
    const reason = (error as Failure)?.error;
    if (reason === "qr_login_already_claimed") return t("wa_qr_approve_already_claimed");
    if (reason === "qr_login_denied") return t("wa_qr_approve_denied");
    if (reason === "qr_login_expired") return t("wa_qr_approve_expired");
    return t("wa_qr_approve_failed");
  }

  async function claim(value: string): Promise<void> {
    stage = "loading";
    message = "";
    number = "";
    try {
      const response = await api("/account/qr-login/claim", {
        method: "POST",
        body: JSON.stringify({ code: value }),
      });
      if (!response.ok) throw response;
      requestId = String(response.request_id || "");
      device =
        [response.browser, response.os].filter(Boolean).join(" · ") ||
        t("wa_qr_approve_unknown_device");
      ip = String(response.ip || "");
      stage = "confirm";
    } catch (error) {
      message = failureMessage(error);
      stage = "failed";
    }
  }

  async function approve(): Promise<void> {
    if (number.length !== 2 || busy) return;
    busy = true;
    message = "";
    try {
      const response = await api("/account/qr-login/approve", {
        method: "POST",
        body: JSON.stringify({ request_id: requestId, number: Number(number) }),
      });
      if (!response.ok) throw response;
      stage = "approved";
    } catch (error) {
      const failure = error as Failure;
      if (failure?.error === "qr_login_wrong_number") {
        message = t("wa_qr_approve_wrong_number", { count: failure.attempts_left ?? 0 });
        number = "";
      } else {
        message = failureMessage(error);
        stage = "failed";
      }
    } finally {
      busy = false;
    }
  }

  async function decline(): Promise<void> {
    busy = true;
    try {
      await api("/account/qr-login/deny", {
        method: "POST",
        body: JSON.stringify({ request_id: requestId }),
      });
    } catch {
      // An undecided request simply expires on its own.
    } finally {
      busy = false;
      stage = "declined";
    }
  }

  function close(): void {
    if (stage === "confirm" && requestId) void decline();
    onclose();
  }

  function keepDigits(): void {
    number = number.replace(/\D/g, "").slice(0, 2);
  }

  $effect(() => {
    const value = code;
    if (!open || !value) return;
    untrack(() => void claim(value));
  });
</script>

<Dialog
  {open}
  title={t("wa_qr_approve_title")}
  closeLabel={t("wa_close")}
  onclose={close}
  class="qr-approve-dialog"
>
  <div class="qr-approve" aria-live="polite">
    {#if stage === "loading"}
      <div class="qr-approve-wait">
        <Spinner />
        <span>{t("wa_qr_approve_loading")}</span>
      </div>
    {:else if stage === "confirm"}
      <dl class="qr-approve-facts">
        <div>
          <dt>{t("wa_qr_approve_device")}</dt>
          <dd>{device}</dd>
        </div>
        {#if ip}
          <div>
            <dt>{t("wa_qr_approve_ip")}</dt>
            <dd>{ip}</dd>
          </div>
        {/if}
      </dl>
      <StatusMessage error class="qr-approve-warning">{t("wa_qr_approve_warning")}</StatusMessage>
      <label class="qr-approve-number">
        <span>{t("wa_qr_approve_number_label")}</span>
        <Input
          bind:value={number}
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength={2}
          placeholder="00"
          oninput={keepDigits}
          onkeydown={(event: KeyboardEvent) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            void approve();
          }}
        />
      </label>
      {#if message}
        <StatusMessage error>{message}</StatusMessage>
      {/if}
    {:else if stage === "approved"}
      <StatusMessage>{t("wa_qr_approve_success")}</StatusMessage>
    {:else if stage === "declined"}
      <StatusMessage>{t("wa_qr_approve_declined")}</StatusMessage>
    {:else}
      <StatusMessage error>{message}</StatusMessage>
    {/if}
  </div>
  {#snippet footer()}
    {#if stage === "confirm"}
      <div class="qr-approve-actions">
        <Button variant="secondary" onclick={decline} disabled={busy}>
          {t("wa_qr_approve_deny")}
        </Button>
        <Button onclick={approve} disabled={busy || number.length !== 2}>
          {t("wa_qr_approve_confirm")}
        </Button>
      </div>
    {:else if stage !== "loading"}
      <Button class="wide" onclick={onclose}>{t("wa_qr_approve_done")}</Button>
    {/if}
  {/snippet}
</Dialog>

<style>
  .qr-approve {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .qr-approve-wait {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-height: 120px;
    color: var(--muted);
  }
  .qr-approve-facts {
    display: grid;
    gap: 8px;
    margin: 0;
  }
  .qr-approve-facts div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }
  .qr-approve-facts dt {
    color: var(--muted);
  }
  .qr-approve-facts dd {
    margin: 0;
    color: var(--text);
    font-weight: 600;
    text-align: right;
    overflow-wrap: anywhere;
  }
  .qr-approve-number {
    display: grid;
    gap: 6px;
    color: var(--muted);
    font-size: 13px;
  }
  .qr-approve-number :global(input) {
    font-size: 28px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.3em;
    text-align: center;
  }
  .qr-approve-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
</style>

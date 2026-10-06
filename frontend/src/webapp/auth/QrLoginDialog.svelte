<script lang="ts">
  /**
   * The waiting side of QR sign-in. It only ever talks to the shop, so it works
   * on a device that cannot reach Telegram: show the code, wait for a signed-in
   * device to scan it, show the number to type there, then open the app.
   */
  import { untrack } from "svelte";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Spinner from "$components/ui/spinner.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import QrCodeTile from "$components/patterns/webapp/QrCodeTile.svelte";
  import {
    cancelQrLogin,
    finishQrLogin,
    pollQrLogin,
    startQrLogin,
    type QrLoginPoll,
  } from "$lib/webapp/qrLogin.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Props = {
    open?: boolean;
    apiBase?: string;
    t: Translate;
    onclose: () => void;
  };
  type Stage = "loading" | "qr" | "scanned" | "approved" | "denied" | "expired" | "error";

  let { open = false, apiBase = "/api", t, onclose }: Props = $props();

  // An unscanned code is replaced quietly a few times, then the user decides.
  const MAX_SILENT_REFRESHES = 5;

  let stage = $state<Stage>("loading");
  let qrUrl = $state("");
  let matchNumber = $state<number | null>(null);
  let requestId = "";
  let pollEveryMs = 2000;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let silentRefreshes = 0;
  let generation = 0;

  function stopPolling(): void {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  function schedule(current: number): void {
    timer = setTimeout(() => void pollOnce(current), pollEveryMs);
  }

  async function begin(silent = false): Promise<void> {
    stopPolling();
    const current = ++generation;
    if (!silent) silentRefreshes = 0;
    stage = "loading";
    matchNumber = null;
    try {
      const started = await startQrLogin(apiBase);
      if (current !== generation) return;
      requestId = started.request_id;
      qrUrl = started.qr_url;
      pollEveryMs = Math.max(1, Number(started.poll_interval) || 2) * 1000;
      stage = "qr";
      schedule(current);
    } catch {
      if (current === generation) stage = "error";
    }
  }

  async function pollOnce(current: number): Promise<void> {
    if (current !== generation) return;
    let result: QrLoginPoll;
    try {
      result = await pollQrLogin(apiBase, requestId);
    } catch {
      if (current === generation) schedule(current);
      return;
    }
    if (current !== generation) return;
    if (result.status === "pending") {
      schedule(current);
    } else if (result.status === "scanned") {
      matchNumber = result.match_number ?? null;
      stage = "scanned";
      schedule(current);
    } else if (result.status === "approved") {
      stage = "approved";
      finishQrLogin();
    } else if (result.status === "denied") {
      stage = "denied";
    } else if (stage === "qr" && silentRefreshes < MAX_SILENT_REFRESHES) {
      silentRefreshes += 1;
      void begin(true);
    } else {
      stage = "expired";
    }
  }

  function close(): void {
    generation += 1;
    stopPolling();
    if (stage !== "approved") void cancelQrLogin(apiBase);
    onclose();
  }

  $effect(() => {
    if (!open) return;
    untrack(() => void begin());
    return () => {
      generation += 1;
      stopPolling();
    };
  });
</script>

<Dialog
  {open}
  title={stage === "scanned" ? t("wa_qr_login_number_title") : t("wa_qr_login_title")}
  description={stage === "qr" ? t("wa_qr_login_hint") : ""}
  closeLabel={t("wa_close")}
  onclose={close}
  class="qr-login-dialog"
>
  <div class="qr-login" aria-live="polite">
    {#if stage === "loading"}
      <div class="qr-login-wait"><Spinner /></div>
    {:else if stage === "qr"}
      <QrCodeTile value={qrUrl} alt={t("wa_qr_login_qr_alt")} />
    {:else if stage === "scanned"}
      <strong class="qr-login-number">{matchNumber}</strong>
      <p class="qr-login-note">{t("wa_qr_login_number_hint")}</p>
    {:else if stage === "approved"}
      <div class="qr-login-wait"><Spinner /></div>
      <StatusMessage>{t("wa_qr_login_success")}</StatusMessage>
    {:else}
      {#if stage === "denied"}
        <StatusMessage error>{t("wa_qr_login_denied")}</StatusMessage>
      {:else if stage === "expired"}
        <StatusMessage error>{t("wa_qr_login_expired")}</StatusMessage>
      {:else}
        <StatusMessage error>{t("wa_qr_login_failed")}</StatusMessage>
      {/if}
      <Button class="wide" onclick={() => void begin()}>{t("wa_qr_login_refresh")}</Button>
    {/if}
  </div>
</Dialog>

<style>
  .qr-login {
    display: grid;
    justify-items: center;
    gap: 12px;
    min-width: 0;
  }
  .qr-login-wait {
    display: grid;
    place-items: center;
    width: min(100%, 280px);
    aspect-ratio: 1;
  }
  .qr-login-number {
    display: grid;
    place-items: center;
    width: min(100%, 280px);
    aspect-ratio: 1.6;
    border-radius: var(--radius-card);
    background: color-mix(in srgb, var(--text) 6%, transparent);
    color: var(--text);
    font-size: 72px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.08em;
  }
  .qr-login-note {
    margin: 0;
    color: var(--muted);
    font-size: 14px;
    text-align: center;
  }
</style>

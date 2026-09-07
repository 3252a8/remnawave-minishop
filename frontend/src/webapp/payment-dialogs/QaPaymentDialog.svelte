<script lang="ts">
  import { CheckCircle2, ShieldCheck, TriangleAlert } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    completeQaPayment,
    fetchQaPaymentState,
    qaPaymentIdFromSearch,
    stripQaPaymentQuery,
    type QaPaymentState,
  } from "$lib/webapp/qaPayment.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    api,
    loadData,
    t,
  }: {
    api: ApiClient["api"];
    loadData: () => Promise<unknown>;
    t: Translate;
  } = $props();

  const paymentId = qaPaymentIdFromSearch(window.location.search);
  let open = $state(new URLSearchParams(window.location.search).has("qa_payment_id"));
  let paymentState = $state<QaPaymentState>(paymentId ? "loading" : "unavailable");
  let busy = $state(false);

  const title = $derived(
    paymentState === "success"
      ? t("wa_qa_payment_success_title")
      : paymentState === "failed"
        ? t("wa_qa_payment_failed_title")
        : paymentState === "unavailable"
          ? t("wa_qa_payment_unavailable_title")
          : t("wa_qa_payment_title")
  );
  const description = $derived(
    paymentState === "success"
      ? t("wa_qa_payment_success_description")
      : paymentState === "failed"
        ? t("wa_qa_payment_failed_description")
        : paymentState === "unavailable"
          ? t("wa_qa_payment_unavailable_description")
          : t("wa_qa_payment_description")
  );

  $effect(() => {
    if (!paymentId) return;
    void fetchQaPaymentState(api, paymentId)
      .then((nextState) => {
        paymentState = nextState;
      })
      .catch(() => {
        paymentState = "unavailable";
      });
  });

  async function complete(): Promise<void> {
    if (!paymentId || busy) return;
    busy = true;
    try {
      paymentState = await completeQaPayment(api, paymentId);
      if (paymentState === "success") await loadData();
    } catch (_error) {
      paymentState = "unavailable";
    } finally {
      busy = false;
    }
  }

  function close(): void {
    open = false;
    window.history.replaceState(null, "", stripQaPaymentQuery(new URL(window.location.href)));
  }
</script>

<Dialog
  {open}
  {title}
  {description}
  closeLabel={t("wa_close")}
  onclose={close}
  class="qa-payment-dialog"
>
  {#snippet titleIcon()}
    {#if paymentState === "success"}
      <CheckCircle2 size={23} />
    {:else if paymentState === "failed" || paymentState === "unavailable"}
      <TriangleAlert size={23} />
    {:else}
      <ShieldCheck size={23} />
    {/if}
  {/snippet}
  <div class="qa-payment-dialog-body">
    <p class="qa-payment-label">{t("wa_qa_payment_dev_label")}</p>
    {#if paymentState === "loading"}
      <Button class="wide" disabled>{t("wa_loading")}</Button>
    {:else if paymentState === "pending"}
      <Button class="wide" disabled={busy} onclick={complete}>
        {busy ? t("wa_qa_payment_completing") : t("wa_qa_payment_complete")}
      </Button>
    {:else}
      <Button class="wide" onclick={close}>{t("wa_ok")}</Button>
    {/if}
  </div>
</Dialog>

<style>
  .qa-payment-dialog-body {
    display: grid;
    gap: 14px;
  }

  .qa-payment-label {
    width: fit-content;
    margin: 0;
    padding: 5px 9px;
    border: 1px solid color-mix(in srgb, var(--accent, #00fe7a) 35%, transparent);
    border-radius: 999px;
    color: var(--muted-foreground, #aeb7c5);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
</style>

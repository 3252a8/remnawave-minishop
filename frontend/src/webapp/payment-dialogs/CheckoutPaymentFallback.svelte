<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { ArrowRight, TriangleAlert } from "$components/ui/icons.js";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { nextCheckoutPaymentMethod } from "$lib/webapp/paymentFallback.js";
  import type { PaymentMethodView, Translate } from "$lib/webapp/types.js";

  let {
    methods,
    failedMethods,
    selectedMethod,
    unavailableMethods = [],
    disabled = false,
    onSelect,
    t,
  }: {
    methods: PaymentMethodView[];
    failedMethods: string[];
    selectedMethod: string;
    unavailableMethods?: string[];
    disabled?: boolean;
    onSelect: (method: string) => void;
    t: Translate;
  } = $props();

  const failedMethod = $derived(failedMethods.at(-1));
  const failedName = $derived(
    String(methods.find((method) => method.id === failedMethod)?.name || t("wa_method_other_title"))
  );
  const nextMethod = $derived(
    nextCheckoutPaymentMethod(methods, failedMethods, unavailableMethods)
  );
  let host = $state<HTMLSpanElement | null>(null);
  let dismissedAttempt = $state.raw<string[] | null>(null);
  const open = $derived(
    Boolean(failedMethod && selectedMethod === failedMethod && failedMethods !== dismissedAttempt)
  );

  function dismiss() {
    dismissedAttempt = failedMethods;
    window.requestAnimationFrame(() => {
      host
        ?.closest(".dialog-card")
        ?.querySelector<HTMLButtonElement>(
          ".payment-method-select-trigger:not(:disabled), .payment-submit-button:not(:disabled)"
        )
        ?.focus();
    });
  }

  function selectAlternative() {
    if (!nextMethod?.id || disabled) return;
    const method = String(nextMethod.id);
    dismiss();
    onSelect(method);
  }
</script>

<span bind:this={host} hidden></span>

{#snippet titleIcon()}
  <span class="fallback-icon"><TriangleAlert size={23} /></span>
{/snippet}

<Dialog
  {open}
  title={t("wa_payment_provider_unavailable_title")}
  closeLabel={t("wa_close")}
  onclose={dismiss}
  showCloseButton={false}
  class="webapp-payment-fallback-dialog"
  portal
  {titleIcon}
>
  <div class="checkout-payment-fallback">
    <StatusMessage role="alert">
      {t("wa_payment_provider_unavailable", { method: failedName })}
    </StatusMessage>
    <p class="fallback-hint">
      {t(nextMethod ? "wa_payment_fallback_hint" : "wa_payment_fallback_none")}
    </p>
    {#if nextMethod}
      <Button
        data-webapp-action="select-payment-alternative"
        {disabled}
        onclick={selectAlternative}
      >
        {t("wa_payment_fallback_select", {
          method: String(nextMethod.name || t("wa_method_other_title")),
        })}
        <ArrowRight size={16} />
      </Button>
    {/if}
    <Button variant={nextMethod ? "secondary" : "default"} onclick={dismiss}>
      {t("wa_payment_fallback_back")}
    </Button>
  </div>
</Dialog>

<style>
  :global(.webapp-payment-fallback-dialog) {
    width: min(100%, 420px);
  }

  .checkout-payment-fallback {
    display: grid;
    gap: 10px;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .fallback-icon {
    display: grid;
    color: var(--danger);
  }

  .checkout-payment-fallback :global(.status-line),
  .fallback-hint {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.45;
  }

  .checkout-payment-fallback :global(.btn) {
    width: 100%;
    white-space: normal;
  }
</style>

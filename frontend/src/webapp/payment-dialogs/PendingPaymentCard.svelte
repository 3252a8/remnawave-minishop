<script lang="ts">
  import { durationParts } from "$lib/webapp/subscriptionPeriods";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { ExternalLink, History, RotateCcw, Tag, TriangleAlert } from "$components/ui/icons.js";
  import { formatCompactNumber } from "$lib/webapp/formatters.js";
  import { priceLabel } from "$lib/webapp/tariffs.js";
  import type { PendingPaymentView, TermUnitLabel, Translate } from "$lib/webapp/types.js";

  let {
    payment,
    payBusy = false,
    resume = () => {},
    cancel = () => {},
    t = (key) => key,
    termUnitLabel = () => "",
  }: {
    payment: PendingPaymentView;
    payBusy?: boolean;
    resume?: (payment: PendingPaymentView) => void;
    cancel?: (payment: PendingPaymentView) => void;
    t?: Translate;
    termUnitLabel?: TermUnitLabel;
  } = $props();

  let cancelConfirmOpen = $state(false);

  function confirmCancel(): void {
    cancelConfirmOpen = false;
    cancel(payment);
  }

  function paymentPrice(value: unknown): string {
    const amount = Number(value || 0);
    const provider = String(payment.provider || "");
    return priceLabel(
      {
        price: amount,
        stars_price: provider.toLowerCase().includes("stars") ? amount : undefined,
        currency: String(payment.currency || ""),
      },
      provider
    );
  }

  function paymentTerm(): string {
    const duration =
      payment.period_semantics === "fixed_days" ? durationParts(payment.duration_days) : null;
    if (duration) return `${duration.count} ${termUnitLabel(duration.count, duration.unit)}`;
    const months = Number(payment.months || 0);
    if (months > 0) return `${months} ${termUnitLabel(months, "month")}`;
    const trafficGb = Number(payment.purchased_gb || 0);
    if (trafficGb > 0) {
      return t("wa_pending_payment_traffic", { gb: formatCompactNumber(trafficGb) });
    }
    const devices = Number(payment.purchased_hwid_devices || 0);
    if (devices > 0) return t("wa_pending_payment_devices", { count: devices });
    return t("wa_pending_payment_purchase");
  }

  function paymentDiscount(): string {
    const summary = String(payment.promo_effect_summary || "").trim();
    if (summary) return summary;
    const percent = Number(payment.discount_percent || 0);
    return percent > 0
      ? t("wa_pending_payment_discount_percent", {
          percent: formatCompactNumber(percent),
        })
      : t("wa_pending_payment_discount_applied");
  }
</script>

<section class="pending-payment-card">
  <div class="pending-payment-heading">
    <div class="pending-payment-title-row">
      <span class="pending-payment-icon"><History size={18} /></span>
      <strong>{t("wa_pending_payment_title")}</strong>
    </div>
    <small class="pending-payment-description">
      {t("wa_pending_payment_description", {
        promo: payment.promo_code || "",
      })}
    </small>
  </div>
  <div class="pending-payment-facts">
    <span>
      <small>{t("wa_pending_payment_term")}</small>
      <strong>{paymentTerm()}</strong>
    </span>
    <span>
      <small>{t("wa_pending_payment_amount")}</small>
      <strong class="pending-payment-price">
        {#if Number(payment.base_amount || 0) > Number(payment.amount || 0)}
          <s>{paymentPrice(payment.base_amount)}</s>
        {/if}
        {paymentPrice(payment.amount)}
      </strong>
    </span>
    <span>
      <small><Tag size={12} /> {t("wa_pending_payment_discount")}</small>
      <strong>{paymentDiscount()}</strong>
    </span>
  </div>
  <Button class="wide pending-payment-action" onclick={() => resume(payment)} disabled={payBusy}>
    {t("wa_pending_payment_continue")}
    <ExternalLink size={16} />
  </Button>
  {#if payment.promo_code}
    <Button
      variant="secondary"
      class="wide pending-payment-reuse-action"
      onclick={() => (cancelConfirmOpen = true)}
      disabled={payBusy}
    >
      <RotateCcw size={16} />
      {t("wa_pending_payment_reuse_promo")}
    </Button>
  {/if}
</section>

{#snippet cancelTitleIcon()}
  <TriangleAlert size={23} />
{/snippet}

<Dialog
  open={cancelConfirmOpen}
  title={t("wa_pending_payment_cancel_title")}
  description={t("wa_pending_payment_cancel_description", {
    promo: payment.promo_code || "",
  })}
  closeLabel={t("wa_close")}
  onclose={() => (cancelConfirmOpen = false)}
  class="payment-dialog-card pending-payment-cancel-dialog"
  showCloseButton={false}
  titleIcon={cancelTitleIcon}
>
  <div class="payment-dialog-body">
    <Button
      variant="outline"
      class="wide device-danger-button"
      onclick={confirmCancel}
      disabled={payBusy}
    >
      <RotateCcw size={17} />
      {t("wa_pending_payment_cancel_yes")}
    </Button>
    <Button
      variant="secondary"
      class="wide"
      onclick={() => (cancelConfirmOpen = false)}
      disabled={payBusy}
    >
      {t("wa_pending_payment_cancel_no")}
    </Button>
  </div>
</Dialog>

<script lang="ts">
  import "./gift-checkout.css";
  import { onMount } from "svelte";
  import { Gift, CheckCircle2, Clock } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Input from "$components/ui/input.svelte";
  import Checkbox from "$components/ui/checkbox.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import { giftState, forgetGift, type GiftView } from "$lib/webapp/gifts.svelte.js";
  import { buildTariffCatalog, firstAvailableMethod } from "$lib/webapp/tariffs.js";
  import type { BillingStore } from "$lib/webapp/stores/billingStore.js";
  import type {
    PaymentMethodView,
    PendingPaymentView,
    PlanView,
    Translate,
    TermUnitLabel,
  } from "$lib/webapp/types.js";
  import PaymentCheckoutDialog from "../payment-dialogs/PaymentCheckoutDialog.svelte";
  import GiftCard from "./GiftCard.svelte";
  import GiftEntry from "./GiftEntry.svelte";

  let {
    api,
    billing,
    userId,
    userLabel = userId,
    loggedIn,
    enabled,
    methods,
    paymentMethodsDisplayMode = "dropdown",
    pendingPayment = null,
    t,
    termUnitLabel,
    onactivated = () => {},
  }: {
    api: ApiClient["api"];
    billing: BillingStore;
    userId: string;
    userLabel?: string;
    loggedIn: boolean;
    enabled?: boolean;
    methods: PaymentMethodView[];
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
    t: Translate;
    termUnitLabel: TermUnitLabel;
    onactivated?: () => unknown;
    pendingPayment?: PendingPaymentView | null;
  } = $props();
  let plans = $state<PlanView[]>([]);
  let preview = $state<GiftView | null>(null);
  let error = $state("");
  let busy = $state(false);
  let copied = $state(false);
  let success = $state(false);
  let previewLoading = $state(false);
  let sendEmail = $state(false);
  let emailAvailable = $state(false);
  let listRequest = 0;
  let previewRequest = 0;
  const catalog = $derived(buildTariffCatalog(plans));
  const tariffMode = $derived(plans.some((plan) => Boolean(plan.tariff_key)));
  const selectedTariff = $derived(
    catalog.find((tariff) => tariff.key === billing.selectedTariffKey) || null
  );
  const selectedPlans = $derived(
    plans.filter((plan) => !tariffMode || plan.tariff_key === billing.selectedTariffKey)
  );
  const paymentMethods = $derived(
    methods.filter(
      (method) =>
        method.id !== "tribute" &&
        !String(method.id).endsWith("_subscription") &&
        !method.price_managed_externally
    )
  );
  const incoming = $derived(Boolean(giftState.token && giftState.incoming));
  const receipt = $derived(
    giftState.gifts.find((gift) => gift.payment_id === giftState.receiptId) || null
  );
  const claimBlocked = $derived(
    preview?.owned && preview.status === "ready"
      ? "gift_own"
      : preview?.status === "revoked"
        ? "gift_unavailable"
        : preview && ["activated", "activating"].includes(preview.status) && !preview.claimed_by_me
          ? "gift_used"
          : preview?.conflict || ""
  );

  function errorKey(value: unknown): string {
    const code = value && typeof value === "object" && "error" in value ? String(value.error) : "";
    return [
      "gift_not_found",
      "gift_unavailable",
      "gift_own",
      "gift_used",
      "gift_tariff_conflict",
      "gift_recurring_conflict",
      "gift_activation_retry",
      "gift_other_activation_pending",
    ].includes(code)
      ? code
      : "gift_activation_retry";
  }

  async function refreshGifts() {
    const request = ++listRequest;
    giftState.loading = true;
    try {
      const data = unwrap(await api("/gifts"));
      if (request !== listRequest) return;
      giftState.gifts = data.gifts;
      giftState.enabled = data.enabled;
      if (data.gifts.some((gift) => gift.payment_id === Number(giftState.pending?.payment_id)))
        giftState.pending = null;
      giftState.error = "";
    } catch {
      if (request === listRequest) giftState.error = "load_failed";
    } finally {
      if (request === listRequest) giftState.loading = false;
    }
  }

  async function loadPreview(token: string) {
    const request = ++previewRequest;
    previewLoading = true;
    preview = null;
    error = "";
    try {
      const response = unwrap(
        await api("/gifts/preview", { method: "POST", body: JSON.stringify({ token }) })
      );
      if (request === previewRequest) {
        preview = response.gift;
        success = preview.status === "activated" && preview.claimed_by_me;
      }
    } catch (value) {
      if (request === previewRequest) error = errorKey(value);
    } finally {
      if (request === previewRequest) previewLoading = false;
    }
  }

  async function purchase() {
    giftState.purchaseRequested = false;
    sendEmail = false;
    busy = true;
    try {
      const options = unwrap(await api("/gifts/options"));
      giftState.enabled = options.enabled;
      if (!options.enabled) throw new Error("gift_purchase_unavailable");
      plans = options.plans as PlanView[];
      emailAvailable = options.email_available;
      giftState.open = false;
      billing.openPaymentModal(
        tariffMode,
        catalog.length === 1,
        catalog,
        {},
        plans,
        firstAvailableMethod(paymentMethods)
      );
      billing.renewHwidDevices = false;
    } catch {
      giftState.open = true;
      error = "gift_purchase_unavailable";
    } finally {
      busy = false;
    }
  }

  async function claim() {
    if (busy || claimBlocked || !preview) return;
    busy = true;
    error = "";
    try {
      unwrap(
        await api("/gifts/claim", {
          method: "POST",
          body: JSON.stringify({ token: giftState.token }),
        })
      );
      success = true;
      await loadPreview(giftState.token);
      await onactivated();
      forgetGift();
      giftState.open = false;
    } catch (value) {
      error = errorKey(value);
    } finally {
      busy = false;
    }
  }

  async function copy(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      copied = true;
    } catch {
      copied = false;
    }
  }

  $effect(() => {
    const revision = giftState.revision;
    if (loggedIn) {
      if (typeof enabled === "boolean") giftState.enabled = enabled;
      void revision;
      void refreshGifts();
    } else {
      ++listRequest;
      giftState.enabled = false;
      giftState.loading = false;
      giftState.error = "";
      giftState.gifts = [];
      giftState.pending = null;
      giftState.receiptId = 0;
    }
  });
  $effect(() => {
    if (loggedIn && giftState.token) {
      giftState.open = true;
      giftState.incoming = true;
      void loadPreview(giftState.token);
    } else {
      ++previewRequest;
      preview = null;
      success = false;
    }
  });
  $effect(() => {
    if (loggedIn && giftState.purchaseRequested && !busy) void purchase();
  });
  $effect(() => {
    if (!sendEmail) giftState.recipientEmail = "";
  });
  $effect(() => {
    if (
      pendingPayment &&
      String(pendingPayment.sale_mode || "")
        .split("|")
        .includes("gift")
    )
      giftState.pending = pendingPayment;
  });
  onMount(() => {
    const resume = () => {
      if (loggedIn) void refreshGifts();
    };
    window.addEventListener("focus", resume);
    return () => window.removeEventListener("focus", resume);
  });
</script>

{#if !loggedIn && giftState.token}
  <aside class="gift-guest">
    <Gift size={26} />
    <div>
      <strong>{t("wa_gift_received_title")}</strong>
      <p>{t("wa_gift_login_description")}</p>
    </div>
  </aside>
{/if}

<Dialog
  class="gift-dialog"
  open={loggedIn && giftState.open}
  title={incoming
    ? t(success ? "wa_gift_activated_title" : "wa_gift_received_title")
    : t("wa_gift_my_gifts")}
  closeLabel={t("wa_close")}
  onclose={() => {
    if (
      incoming &&
      (success ||
        error === "gift_not_found" ||
        ["gift_own", "gift_used", "gift_unavailable"].includes(claimBlocked))
    )
      forgetGift();
    if (receipt) giftState.receiptId = 0;
    giftState.open = false;
  }}
>
  {#if incoming}
    <div class="gift-receive">
      <div class="gift-hero" class:success>
        {#if success}<CheckCircle2 size={44} />{:else}<Gift size={44} />{/if}
      </div>
      {#if !claimBlocked && !error && (success || preview)}<p class="gift-lead">
          {t(success ? "wa_gift_activated_description" : "wa_gift_receive_description")}
        </p>{/if}
      {#if previewLoading}<p role="status">{t("wa_loading")}</p>{/if}
      {#if preview && !["gift_used", "gift_unavailable"].includes(claimBlocked)}<GiftCard
          gift={preview}
          {t}
          oncopy={copy}
        />{/if}
      {#if preview?.extends_subscription && !success}<p class="gift-hint">
          {t("wa_gift_extension_note")}
        </p>{/if}
      {#if error || claimBlocked}<p class="gift-error" role="alert">
          {t(`wa_${error || claimBlocked}`)}
        </p>{/if}
      {#if copied}<p role="status">{t("wa_link_copied")}</p>{/if}
      {#if success}<Button
          onclick={() => {
            forgetGift();
            giftState.open = false;
          }}>{t("wa_gift_go_account")}</Button
        >
      {:else if preview && !claimBlocked}<p class="gift-hint">
          {t("wa_gift_confirm_account", { account: userLabel })}
        </p>
        <Button disabled={busy} onclick={claim}
          >{t(
            busy
              ? "wa_gift_activating"
              : error === "gift_activation_retry"
                ? "wa_gift_retry"
                : "wa_gift_activate"
          )}</Button
        >
      {:else if !preview && error}<Button
          variant="secondary"
          onclick={() => loadPreview(giftState.token)}>{t("wa_gift_retry")}</Button
        >{/if}
      {#if !success && !["gift_used", "gift_unavailable"].includes(claimBlocked) && error !== "gift_not_found"}<Button
          variant="secondary"
          onclick={() => (giftState.open = false)}>{t("wa_gift_later")}</Button
        >{/if}
    </div>
  {:else if receipt}
    <div class="gift-receive">
      <div class="gift-hero"><Gift size={44} /></div>
      <h2 class="gift-ready-title">{t("wa_gift_ready_title")}</h2>
      <p class="gift-lead">{t("wa_gift_ready_description")}</p>
      <GiftCard gift={receipt} {t} oncopy={copy} />{#if copied}<p role="status">
          {t("wa_link_copied")}
        </p>{/if}
    </div>
  {:else}
    {#if giftState.pending || giftState.receiptId}
      <div class="gift-receive gift-payment-pending">
        <div class="gift-hero"><Clock size={32} /></div>
        <h2 class="gift-ready-title">{t("wa_gift_payment_pending")}</h2>
        <p class="gift-lead">{t("wa_gift_payment_pending_description")}</p>
        <div class="gift-pending-actions">
          <Button
            disabled={!giftState.pending || billing.payBusy}
            onclick={() => giftState.pending && billing.resumePendingPayment(giftState.pending)}
            >{t("wa_gift_payment_reopen")}</Button
          >
        </div>
      </div>
    {/if}
    {#if error}<p class="gift-error" role="alert">{t(`wa_${error}`)}</p>{/if}
    {#if !giftState.pending && !giftState.receiptId}<GiftEntry {t} full />{/if}
  {/if}
</Dialog>

<PaymentCheckoutDialog
  {api}
  gift
  {t}
  {termUnitLabel}
  {plans}
  {tariffMode}
  {selectedTariff}
  tariffCatalog={catalog}
  selectedTariffPlans={selectedPlans}
  methods={paymentMethods}
  {paymentMethodsDisplayMode}
  singleTariffMode={catalog.length === 1}
  hasMultipleTariffs={catalog.length > 1}
  bind:paymentModalOpen={billing.paymentModalOpen}
  bind:paymentStep={billing.paymentStep}
  bind:selectedPlan={billing.selectedPlan}
  bind:selectedMethod={billing.selectedMethod}
  bind:selectedTariffKey={billing.selectedTariffKey}
  renewHwidDevices={false}
  payBusy={billing.payBusy}
  subscriptionPurchaseDescription={t("wa_gift_purchase_note")}
  closePaymentModal={billing.closePaymentModal}
  selectTariff={(tariff) => billing.selectTariff(tariff, plans)}
  continueWithSelectedTariff={() => billing.continueWithSelectedTariff(selectedPlans)}
  backToTariffList={() => billing.backToTariffList({}, catalog)}
  createPayment={(options) => {
    const emailInput = document.getElementById("gift-recipient-email");
    if (sendEmail && emailInput instanceof HTMLInputElement && !emailInput.reportValidity()) return;
    return billing.createPayment(options);
  }}
  checkoutPromoInput={billing.checkoutPromoInput}
  checkoutPromoAppliedCode={billing.checkoutPromoAppliedCode}
  checkoutPromoIsError={billing.checkoutPromoIsError}
  checkoutPromoPriceText={billing.checkoutPromoPriceText}
  checkoutPromoEffectiveAmount={billing.checkoutPromoEffectiveAmount}
  checkoutPromoStatus={billing.checkoutPromoStatus}
  checkoutPromoDiscountPercent={billing.checkoutPromoDiscountPercent}
  checkoutPromoAppliesTo={billing.checkoutPromoAppliesTo}
  checkoutPromoMinSubscriptionDays={billing.checkoutPromoMinSubscriptionDays}
  checkoutPromoMinTrafficGb={billing.checkoutPromoMinTrafficGb}
  setCheckoutPromoInput={billing.setCheckoutPromoInput}
  applyCheckoutPromo={billing.applyCheckoutPromo}
  clearCheckoutPromo={billing.clearCheckoutPromo}
  {giftDelivery}
/>

{#snippet giftDelivery()}
  {#if emailAvailable}
    <div class="gift-email">
      <label class="gift-email-toggle"
        ><Checkbox bind:checked={sendEmail} />{t("wa_gift_send_email")}</label
      >
      {#if sendEmail}<Input
          id="gift-recipient-email"
          aria-label={t("wa_gift_recipient_email")}
          type="email"
          required
          autocomplete="off"
          bind:value={giftState.recipientEmail}
          placeholder={t("wa_gift_recipient_email")}
        />
      {/if}
    </div>
  {/if}
{/snippet}

<style>
  .gift-email {
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    padding: 10px;
    display: grid;
    gap: 10px;
    font-size: 13px;
  }
  .gift-email-toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 600;
  }
  .gift-guest {
    margin: 20px auto 0;
    box-sizing: border-box;
    width: calc(100% - 32px);
    max-width: 480px;
    display: flex;
    gap: 14px;
    align-items: center;
    padding: 18px;
    border-radius: var(--radius-card);
    background: color-mix(in srgb, var(--accent) 10%, var(--panel));
    color: var(--accent);
  }
  .gift-guest p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    margin: 5px 0 0;
  }
  .gift-receive {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
    gap: 12px;
  }
  .gift-ready-title {
    font-size: 20px;
    text-align: center;
    margin: 0;
  }
  .gift-payment-pending {
    gap: 16px;
  }
  .gift-pending-actions {
    display: grid;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  :global(.gift-dialog > .dialog-body-scroll),
  :global(.gift-dialog .scroll-area__viewport),
  :global(.gift-dialog .scroll-area__viewport > div) {
    min-width: 0;
    max-width: 100%;
  }
  :global(.gift-dialog .scroll-area__viewport > div) {
    display: block !important;
  }
  .gift-hero {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 60px;
    height: 60px;
    margin: 0 auto;
    border-radius: var(--radius-card);
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }
  .gift-hero.success {
    color: var(--success, #22c55e);
  }
  .gift-lead {
    text-align: center;
    color: var(--muted);
    line-height: 1.45;
    margin: 0;
  }
  .gift-error {
    color: var(--danger);
    background: color-mix(in srgb, var(--danger) 8%, transparent);
    padding: 14px;
    border-radius: var(--radius-inner);
    font-size: 13px;
    line-height: 1.6;
    margin: 0;
  }
  .gift-hint {
    font-size: 12px;
    line-height: 1.5;
    color: var(--muted);
    margin: 0;
  }
</style>

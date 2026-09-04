<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import EmailCodeScreen from "../auth/EmailCodeScreen.svelte";
  import CheckoutTariffPicker from "../payment-dialogs/CheckoutTariffPicker.svelte";
  import type { CheckoutDeeplink } from "$lib/webapp/deeplinks.js";
  import { writeCheckoutPlanToUrl } from "$lib/webapp/deeplinks.js";
  import {
    buildTariffCatalog,
    initialCheckoutTariffKey,
    priceLabel,
    type TariffCatalogEntry,
  } from "$lib/webapp/tariffs.js";
  import type { PlanView, TariffView, WebappRecord } from "$lib/webapp/types.js";
  import type { Snippet } from "svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Action = () => void | Promise<void>;

  type Props = {
    authBusy?: boolean;
    authIsError?: boolean;
    authResendCooldown?: number;
    authStatus?: string;
    brand?: WebappRecord;
    brandTitle?: string;
    clearLoginEmailError?: (event?: Event) => void;
    children?: Snippet;
    canChangePaymentPlan?: boolean;
    deeplink?: CheckoutDeeplink | null;
    email?: string;
    emailCode?: string;
    loginEmailFieldError?: string;
    onBackToEmail?: Action;
    onChangePaymentPlan?: Action;
    openExternalLink?: (url: string) => void;
    pendingEmail?: string;
    plans?: PlanView[];
    privacyPolicyUrl?: string;
    paymentPlan?: PlanView | null;
    paymentStep?: string;
    paymentTariff?: TariffView | null;
    requestEmailCode?: Action;
    screen?: string;
    submitEmailOnEnter?: (event: KeyboardEvent) => void;
    t: Translate;
    userAgreementUrl?: string;
    verifyEmailCode?: Action;
    flowStep?: "identity" | "payment";
  };

  let {
    screen = "login",
    brand = {},
    brandTitle = "",
    plans = [],
    deeplink = null,
    email = $bindable(""),
    emailCode = $bindable(""),
    pendingEmail = "",
    authStatus = "",
    authIsError = false,
    authBusy = false,
    authResendCooldown = 0,
    loginEmailFieldError = "",
    children,
    canChangePaymentPlan = false,
    privacyPolicyUrl = "",
    userAgreementUrl = "",
    paymentPlan = null,
    paymentStep = "checkout",
    paymentTariff = null,
    requestEmailCode = () => {},
    verifyEmailCode = () => {},
    onBackToEmail = () => {},
    onChangePaymentPlan = () => {},
    clearLoginEmailError = () => {},
    openExternalLink = () => {},
    submitEmailOnEnter = () => {},
    t,
    flowStep = "identity",
  }: Props = $props();

  const catalog = $derived(buildTariffCatalog(plans));
  const linkedPlan = $derived.by(() => {
    const requested = String(deeplink?.plan || "").trim();
    if (!requested) return null;
    const requestedMonths = Number(deeplink?.months || 0);
    return (
      plans.find((plan) => String(plan.id ?? "") === requested) ||
      plans.find(
        (plan) =>
          String(plan.tariff_key || "") === requested &&
          (!requestedMonths || Number(plan.months || 0) === requestedMonths)
      ) ||
      null
    );
  });

  let selectedTariffKey = $state("");
  let planPickerOpen = $state(false);

  $effect(() => {
    if (selectedTariffKey) return;
    const key = initialCheckoutTariffKey(catalog, linkedPlan);
    if (key) {
      selectedTariffKey = key;
      planPickerOpen = false;
    } else {
      planPickerOpen = true;
    }
  });

  const selectedTariff = $derived(catalog.find((entry) => entry.key === selectedTariffKey) || null);
  const selectedPlan = $derived.by(() => {
    if (!selectedTariff) return null;
    const requestedMonths = Number(deeplink?.months || 0);
    const candidates = plans
      .filter((plan) => String(plan.tariff_key || "") === selectedTariff.key)
      .sort((left, right) => Number(left.months || 0) - Number(right.months || 0));
    return (
      candidates.find((plan) => requestedMonths && Number(plan.months || 0) === requestedMonths) ||
      candidates[0] ||
      null
    );
  });
  const choosingPlan = $derived(planPickerOpen || !selectedTariff);
  const confirmingCode = $derived(screen === "code");
  const inPaymentFlow = $derived(flowStep === "payment");
  const editingPaymentPlan = $derived(inPaymentFlow && paymentStep === "tariff");
  const trackTariff = $derived(inPaymentFlow ? paymentTariff : selectedTariff);
  const trackPlan = $derived(inPaymentFlow ? paymentPlan : selectedPlan);

  function changePlan() {
    if (inPaymentFlow) onChangePaymentPlan();
    else planPickerOpen = true;
  }

  function selectPlan(entry: TariffCatalogEntry) {
    selectedTariffKey = entry.key;
    planPickerOpen = false;
    writeCheckoutPlanToUrl(entry.key);
  }

  function planPrice(entry: TariffCatalogEntry): string {
    const plan = plans
      .filter((item) => String(item.tariff_key || "") === entry.key)
      .sort((left, right) => Number(left.months || 0) - Number(right.months || 0))[0];
    return priceLabel(plan);
  }

  function requestCode() {
    if (!choosingPlan) requestEmailCode();
  }

  const checkoutOptions = $derived(
    [
      deeplink?.addons.deviceTotal != null
        ? t("wa_checkout_option_devices", { count: deeplink.addons.deviceTotal })
        : "",
      deeplink?.addons.regularLimitGb != null
        ? t("wa_checkout_option_regular", { gb: deeplink.addons.regularLimitGb })
        : "",
      deeplink?.addons.premiumLimitGb != null
        ? t("wa_checkout_option_premium", { gb: deeplink.addons.premiumLimitGb })
        : "",
    ].filter(Boolean)
  );
</script>

<div class="checkout-entry">
  <aside class="checkout-side">
    <a class="checkout-brand" href="/" aria-label={brandTitle}>
      <BrandMark {brand} size="md" />
      <strong>{brandTitle}</strong>
    </a>
    <div class="checkout-steps">
      <h2>{t("wa_checkout_steps_title")}</h2>
      <ol>
        <li
          class:complete={inPaymentFlow ? !editingPaymentPlan : !choosingPlan}
          class:active={inPaymentFlow ? editingPaymentPlan : choosingPlan}
        >
          <span class="step-dot"
            >{inPaymentFlow ? (editingPaymentPlan ? "1" : "✓") : choosingPlan ? "1" : "✓"}</span
          >
          <div>
            <strong>{t("wa_checkout_step_plan")}</strong>
            {#if trackTariff && !(inPaymentFlow ? editingPaymentPlan : choosingPlan)}
              <small>{trackTariff.title} · {priceLabel(trackPlan)}</small>
              {#if !inPaymentFlow || canChangePaymentPlan}
                <button class="side-change" type="button" onclick={changePlan}>
                  {t("wa_checkout_change_plan")}
                </button>
              {/if}
            {/if}
          </div>
        </li>
        <li class:complete={inPaymentFlow} class:active={!inPaymentFlow && !choosingPlan}>
          <span class="step-dot">{inPaymentFlow ? "✓" : "2"}</span><strong
            >{t("wa_checkout_step_email")}</strong
          >
        </li>
        <li class:active={inPaymentFlow && !editingPaymentPlan}>
          <span class="step-dot">3</span><strong>{t("wa_checkout_step_payment")}</strong>
        </li>
        <li>
          <span class="step-dot">4</span><strong>{t("wa_checkout_step_install")}</strong>
        </li>
      </ol>
    </div>
  </aside>

  <main class="checkout-main">
    <div class="checkout-notice">
      <span aria-hidden="true">ⓘ</span>
      <strong>{t("wa_checkout_notice")}</strong>
    </div>

    <div class="checkout-stage" class:payment-stage={inPaymentFlow}>
      <section class="checkout-card" class:payment-card={inPaymentFlow}>
        {#if inPaymentFlow}
          {@render children?.()}
        {:else if choosingPlan}
          <header>
            <h1>{t("wa_checkout_choose_plan_title")}</h1>
            <p>{t("wa_checkout_choose_plan_description")}</p>
          </header>
          <CheckoutTariffPicker
            tariffs={catalog}
            {selectedTariffKey}
            metaLabel={(entry) => t("wa_checkout_price_from", { price: planPrice(entry) })}
            selectTariff={selectPlan}
            {t}
          />
        {:else if confirmingCode}
          <EmailCodeScreen
            embedded
            bind:code={emailCode}
            email={pendingEmail}
            busy={authBusy}
            resendCooldown={authResendCooldown}
            status={authStatus}
            isError={authIsError}
            {t}
            onBack={onBackToEmail}
            onConfirm={verifyEmailCode}
            onResend={requestEmailCode}
          />
        {:else}
          <header>
            <h1>{t("wa_checkout_guest_email_title")}</h1>
            <p>{t("wa_checkout_guest_email_description")}</p>
          </header>
          <label class="email-field">
            <input
              bind:value={email}
              type="email"
              autocomplete="email"
              placeholder={t("wa_email_placeholder")}
              aria-invalid={Boolean(loginEmailFieldError)}
              oninput={clearLoginEmailError}
              onkeydown={submitEmailOnEnter}
            />
            {#if loginEmailFieldError}<small>{loginEmailFieldError}</small>{/if}
          </label>
          <button class="primary-button" type="button" onclick={requestCode} disabled={authBusy}>
            {t("wa_checkout_guest_send_code")}
          </button>
          {#if privacyPolicyUrl || userAgreementUrl}
            <p class="legal-note">
              {t("wa_auth_legal_intro")}
              {#if privacyPolicyUrl}
                <button type="button" onclick={() => openExternalLink(privacyPolicyUrl)}
                  >{t("wa_auth_legal_privacy")}</button
                >
              {/if}
              {#if privacyPolicyUrl && userAgreementUrl}
                ·
              {/if}
              {#if userAgreementUrl}
                <button type="button" onclick={() => openExternalLink(userAgreementUrl)}
                  >{t("wa_auth_legal_agreement")}</button
                >
              {/if}
            </p>
          {/if}
        {/if}

        {#if authStatus && !confirmingCode}
          <p class:error={authIsError} class="checkout-status">{authStatus}</p>
        {/if}
      </section>

      {#if !inPaymentFlow && selectedTariff && !choosingPlan}
        <div class="mobile-plan-summary">
          <span>{t("wa_checkout_selected_plan")}: <strong>{selectedTariff.title}</strong></span>
          <span>{priceLabel(selectedPlan)}</span>
          <button type="button" onclick={() => (planPickerOpen = true)}
            >{t("wa_checkout_change_plan")}</button
          >
          {#if checkoutOptions.length}
            <div class="checkout-options">
              {#each checkoutOptions as option}<small>{option}</small>{/each}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  </main>
</div>

<style>
  .checkout-entry {
    min-height: 100dvh;
    display: grid;
    grid-template-columns: 330px minmax(0, 1fr);
    background: var(--bg);
    color: var(--text);
  }

  .checkout-side {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    padding: 32px;
    border-right: 1px solid var(--border);
    background: color-mix(in srgb, var(--panel) 96%, #000);
  }

  .checkout-brand {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    width: fit-content;
    color: var(--text);
    text-decoration: none;
    font-size: 18px;
  }

  .checkout-steps {
    margin-block: auto;
  }

  .checkout-steps h2 {
    margin: 0 0 26px;
    font-size: 20px;
  }

  .checkout-steps ol {
    display: grid;
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .checkout-steps li {
    position: relative;
    display: grid;
    grid-template-columns: 30px 1fr;
    align-items: start;
    gap: 12px;
    min-height: 66px;
    color: var(--muted);
  }

  .checkout-steps li:not(:last-child)::after {
    content: "";
    position: absolute;
    left: 13px;
    top: 30px;
    bottom: 4px;
    width: 2px;
    background: var(--border);
  }

  .checkout-steps li.active,
  .checkout-steps li.complete {
    color: var(--text);
  }

  .checkout-steps li.complete:not(:last-child)::after {
    background: color-mix(in srgb, var(--accent) 58%, var(--border));
  }

  .step-dot {
    position: relative;
    z-index: 1;
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border: 2px solid var(--border);
    border-radius: 999px;
    background: var(--panel);
    font-size: 12px;
    font-weight: 700;
  }

  li.active .step-dot {
    border-color: var(--accent);
    color: var(--accent);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 12%, transparent);
  }

  li.complete .step-dot {
    border-color: color-mix(in srgb, var(--accent) 62%, #0a6b3a);
    background: color-mix(in srgb, var(--accent) 42%, #06391f);
    color: white;
  }

  .checkout-steps strong,
  .checkout-steps small {
    display: block;
  }

  .checkout-steps strong {
    padding-top: 4px;
    font-size: 15px;
  }

  .checkout-steps small {
    margin-top: 6px;
    color: var(--muted);
    line-height: 1.35;
  }

  .side-change {
    margin: 5px 0 0;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--accent);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  .checkout-main {
    position: relative;
    display: grid;
    grid-template-rows: auto 1fr;
    min-width: 0;
    min-height: 100dvh;
    overflow-x: hidden;
    background: radial-gradient(
      circle at 50% 42%,
      color-mix(in srgb, var(--accent) 8%, transparent),
      transparent 38%
    );
  }

  .checkout-main::before {
    content: "";
    position: absolute;
    inset: 48px 0 0;
    background: linear-gradient(
      135deg,
      transparent 20%,
      color-mix(in srgb, var(--accent) 4%, transparent),
      transparent 75%
    );
    pointer-events: none;
  }

  .checkout-notice {
    position: relative;
    z-index: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    min-height: 48px;
    box-sizing: border-box;
    margin: 16px 20px 0;
    padding: 0 20px;
    border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--border));
    border-radius: 14px;
    background: color-mix(in srgb, var(--accent) 5%, var(--panel));
    color: var(--text);
    font-size: 14px;
    text-align: center;
  }

  .checkout-notice span {
    color: var(--accent);
  }

  .checkout-stage {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 18px;
    width: min(100%, 760px);
    margin: 0 auto;
    padding: 44px 28px;
  }

  .checkout-card {
    position: relative;
    width: min(100%, 590px);
    padding: 42px;
    border: 1px solid color-mix(in srgb, var(--text) 18%, var(--border));
    border-radius: 24px;
    background: color-mix(in srgb, var(--panel) 96%, transparent);
    box-shadow: 0 28px 80px rgba(0, 0, 0, 0.24);
  }

  .checkout-card.payment-card {
    width: min(100%, 680px);
    padding: 32px;
  }

  .checkout-card header {
    margin-bottom: 28px;
    text-align: center;
  }

  .checkout-card h1 {
    margin: 0;
    font-size: clamp(27px, 3vw, 36px);
    line-height: 1.15;
  }

  .checkout-card header p {
    max-width: 460px;
    margin: 15px auto 0;
    color: var(--muted);
    line-height: 1.55;
  }

  .email-field {
    display: grid;
    gap: 7px;
  }

  .email-field input {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--input-bg, var(--surface-muted));
    color: var(--text);
    font: inherit;
    outline: none;
  }

  .email-field input {
    height: 54px;
    padding: 0 17px;
    font-size: 17px;
  }

  .email-field input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .email-field input[aria-invalid="true"] {
    border-color: var(--danger);
  }

  .email-field small,
  .checkout-status.error {
    color: var(--danger);
  }

  .primary-button {
    width: 100%;
    min-height: 54px;
    margin-top: 18px;
    border-radius: 999px;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  .primary-button {
    border: 1px solid var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    color: var(--accent);
  }

  .primary-button:hover:not(:disabled) {
    transform: translateY(-1px);
    filter: brightness(1.08);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .legal-note button,
  .mobile-plan-summary button {
    border: 0;
    background: transparent;
    color: var(--accent);
    font: inherit;
    cursor: pointer;
  }

  .legal-note,
  .checkout-status {
    margin: 18px 0 0;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
    text-align: center;
  }

  .mobile-plan-summary {
    display: none;
  }

  @media (max-width: 780px) {
    .checkout-entry {
      display: block;
    }

    .checkout-side {
      display: none;
    }

    .checkout-main {
      min-height: 100dvh;
    }

    .checkout-notice {
      min-height: 72px;
      margin: 12px 12px 0;
      padding: 10px 20px;
      font-size: 15px;
      line-height: 1.4;
    }

    .checkout-stage {
      justify-content: flex-start;
      box-sizing: border-box;
      padding: 56px 20px 28px;
    }

    .checkout-card {
      box-sizing: border-box;
      padding: 34px 24px;
      border-radius: 22px;
    }

    .checkout-card.payment-card {
      padding: 28px 20px;
    }

    .checkout-card h1 {
      font-size: 29px;
    }

    .checkout-card header p {
      font-size: 15px;
    }

    .mobile-plan-summary {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 6px 12px;
      color: var(--muted);
      font-size: 14px;
      text-align: center;
    }

    .mobile-plan-summary button {
      padding: 0;
    }

    .checkout-options {
      display: flex;
      flex-basis: 100%;
      flex-wrap: wrap;
      justify-content: center;
      gap: 6px;
    }

    .checkout-options small {
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--surface-muted);
    }
  }

  @media (max-width: 390px) {
    .checkout-stage {
      padding-inline: 12px;
    }

    .checkout-card {
      padding-inline: 18px;
    }
  }
</style>

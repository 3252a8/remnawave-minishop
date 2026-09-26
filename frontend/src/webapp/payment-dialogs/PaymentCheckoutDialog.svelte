<script lang="ts">
  import CheckoutHeader from "./CheckoutHeader.svelte";
  import { checkoutUnitPrice } from "$lib/webapp/checkoutUnitPrice.js";
  import { ArrowLeft, ArrowRight, CheckCircle2 } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Checkbox from "$components/ui/checkbox.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { CheckoutAddonSliders, EmptyCard } from "$components/patterns/webapp/index.js";
  import CheckoutPeriodPrice from "./CheckoutPeriodPrice.svelte";
  import CheckoutPaymentControls from "./CheckoutPaymentControls.svelte";
  import CheckoutTariffPicker from "./CheckoutTariffPicker.svelte";
  import PendingPaymentCard from "./PendingPaymentCard.svelte";
  import TrialPaymentSummary from "./TrialPaymentSummary.svelte";
  import type {
    CheckoutPaymentOptions,
    PaymentCheckoutDialogProps,
  } from "./PaymentCheckoutDialog.types.js";
  import {
    checkoutPromoAffectsQuotedPlan,
    checkoutPromoBlockVisible,
    checkoutPromoMatchesPlan,
    discountedCheckoutPlan as discountedCheckoutPlanFn,
    normalizedCheckoutPromoDiscount,
    selectPaymentMethodWithPromoReset,
  } from "$lib/webapp/checkoutPromoPolicy.js";
  import {
    checkoutBalanceLookupPlan,
    createCheckoutBalancePreload,
  } from "$lib/webapp/checkoutBalancePreload.svelte.js";
  import { formatCompactNumber, formatMoney } from "$lib/webapp/formatters.js";
  import { buildSubscriptionQuotePath, type PostPayload } from "$lib/webapp/publicApi.js";
  import * as wataCheckout from "$lib/webapp/wataSubscriptionCheckout.js";
  import {
    planKey as planKeyFn,
    planDisplayTitle as planDisplayTitleFn,
    planSubtitle as planSubtitleFn,
    planUnitHint as planUnitHintFn,
    tariffLimitLabel as tariffLimitLabelFn,
    priceLabel as priceLabelFn,
    firstAvailableMethod,
    isTrialPaymentPlan,
    methodSelectable,
    methodsForPlan,
  } from "$lib/webapp/tariffs.js";
  import type {
    CheckoutAddonDefinition,
    CheckoutAddonKind,
    CheckoutAddonSelection,
    PlanView,
    TariffView,
  } from "$lib/webapp/types.js";
  let {
    api,
    inline = false,
    gift = false,
    giftDelivery,
    createPayment = () => {},
    hasMultipleTariffs = false,
    methods = [],
    paymentMethodsDisplayMode = "dropdown",
    pendingPayment = null,
    payBusy = false,
    paymentModalOpen = $bindable(false),
    paymentStep = $bindable("tariff"),
    plans = [],
    selectedMethod = $bindable(""),
    selectedPlan = $bindable(null),
    selectedTariff = null,
    selectedTariffKey = $bindable(""),
    selectedTariffPlans = [],
    renewHwidDevices = $bindable(true),
    singleTariffMode = false,
    subscription = {},
    subscriptionPurchaseDescription = "",
    tariffCatalog = [],
    tariffMode = false,
    trafficMode = false,
    checkoutAddonValueAnimationEnabled = true,
    checkoutAddonEditorExpandedByDefault = false,
    closePaymentModal = () => {},
    checkoutPromoAppliedCode = "",
    checkoutPromoInput = "",
    checkoutPromoIsError = false,
    checkoutPromoPriceText = "",
    checkoutPromoEffectiveAmount = 0,
    checkoutPromoStatus = "",
    checkoutPromoDiscountPercent = 0,
    checkoutPromoAppliesTo = "all",
    checkoutPromoMinSubscriptionDays = null,
    checkoutPromoMinTrafficGb = null,
    checkoutAddonPreset = null,
    applyCheckoutPromo = () => {},
    backToTariffList = () => {},
    clearCheckoutPromo = () => {},
    continueWithSelectedTariff = () => {},
    resumePendingPayment = () => {},
    cancelPendingPayment = () => {},
    selectTariff = () => {},
    setCheckoutPromoInput = () => {},
    t = (key) => key,
    termUnitLabel = () => "",
  }: PaymentCheckoutDialogProps = $props();

  const methodUsesStars = () =>
    String(selectedMethod || "")
      .toLowerCase()
      .includes("stars");
  function providerManagesPrice() {
    const normalizedMethod = String(selectedMethod || "").toLowerCase();
    if (
      selectedPlan?.externally_managed_price_method_ids?.some(
        (methodId) => String(methodId).toLowerCase() === normalizedMethod
      )
    ) {
      return true;
    }
    return Boolean(
      methods.find((method) => String(method.id || "").toLowerCase() === normalizedMethod)
        ?.price_managed_externally
    );
  }
  function tributeShopSubscriptionSelected(methodId = selectedMethod) {
    return (
      String(methodId || "").toLowerCase() === "tribute" &&
      !providerManagesPrice() &&
      isSubscriptionPlan(selectedPlan)
    );
  }
  function selectPaymentMethod(methodId: string) {
    selectPaymentMethodWithPromoReset(
      methodId,
      selectedPlan,
      (nextMethod) => (selectedMethod = nextMethod),
      clearCheckoutPromo
    );
  }
  let checkoutDeviceCount = $state(0);
  let checkoutRegularLimitGb = $state<number | null>(null);
  let checkoutPremiumLimitGb = $state<number | null>(null);
  let checkoutPlanIdentity = $state("");
  let checkoutQuote = $state<Record<string, unknown> | null>(null);
  let checkoutQuoteBusy = $state(false);
  let checkoutQuoteError = $state("");
  let checkoutQuoteRequestId = 0;
  let checkoutSliderInteracting = $state(false);
  const checkoutAddonSelection = $derived<CheckoutAddonSelection>({
    device_count: checkoutDeviceCount,
    regular_limit_gb: checkoutRegularLimitGb,
    premium_limit_gb: checkoutPremiumLimitGb,
  });
  function checkoutAddonDefinitions(
    plan: PlanView | null
  ): Partial<Record<CheckoutAddonKind, CheckoutAddonDefinition>> {
    if (!isSubscriptionPlan(plan)) return {};
    const definitions = plan?.checkout_addons || {};
    if (!methodUsesStars()) return definitions;
    const supported: Partial<Record<CheckoutAddonKind, CheckoutAddonDefinition>> = {};
    for (const kind of ["devices", "traffic", "premium_traffic"] as CheckoutAddonKind[]) {
      const definition = definitions[kind];
      if (!definition) continue;
      const options = definition.options.filter(
        (option) => Number(option.extra_units || 0) <= 0 || Number(option.stars_price || 0) > 0
      );
      if (options.length > 1) supported[kind] = { ...definition, options };
    }
    return supported;
  }

  function selectedAddonOption(plan: PlanView | null, kind: CheckoutAddonKind) {
    const definitions = checkoutAddonDefinitions(plan);
    const selected =
      kind === "devices"
        ? checkoutDeviceCount
        : kind === "traffic"
          ? checkoutRegularLimitGb
          : checkoutPremiumLimitGb;
    return definitions[kind]?.options?.find(
      (option) =>
        Math.abs(
          Number(kind === "devices" ? option.extra_units || 0 : option.total_units || 0) -
            Number(selected || 0)
        ) < 1e-9
    );
  }

  function planWithSelectedCheckoutAddons(plan: PlanView | null): PlanView | null {
    if (!plan) return plan;
    const next: PlanView = { ...plan };
    for (const kind of ["devices", "traffic", "premium_traffic"] as CheckoutAddonKind[]) {
      const option = selectedAddonOption(plan, kind);
      next.price = Number(next.price || 0) + Number(option?.price || 0);
      if (Number(next.stars_price || 0) > 0) {
        next.stars_price = Number(next.stars_price || 0) + Number(option?.stars_price || 0);
      }
    }
    return next;
  }

  function checkoutAddonsSelected(): boolean {
    if (checkoutDeviceCount > 0) return true;
    const definitions = checkoutAddonDefinitions(selectedPlan);
    for (const kind of ["traffic", "premium_traffic"] as CheckoutAddonKind[]) {
      const definition = definitions[kind];
      const option = selectedAddonOption(selectedPlan, kind);
      if (!definition || !option) continue;
      const initialUnits = Number(definition.initial_units ?? definition.base_units ?? 0);
      const selectedUnits = Number(option.total_units || 0);
      if (Number(option.extra_units || 0) > 0 || Math.abs(selectedUnits - initialUnits) > 1e-9) {
        return true;
      }
    }
    return false;
  }

  function checkoutAddonsUnavailableForMethod(plan: PlanView | null): boolean {
    const method = String(selectedMethod || "").toLowerCase();
    return Boolean(
      method &&
      plan?.checkout_addons_unavailable_payment_method_ids?.some(
        (methodId) => String(methodId).toLowerCase() === method
      )
    );
  }

  function updateCheckoutAddon(kind: CheckoutAddonKind, value: number): void {
    checkoutQuote = null;
    checkoutQuoteError = "";
    if (kind === "devices") {
      checkoutDeviceCount = value;
      if (value > 0) renewHwidDevices = false;
    } else if (kind === "traffic") {
      checkoutRegularLimitGb = value;
    } else {
      checkoutPremiumLimitGb = value;
    }
  }

  function checkoutPresetValue(
    kind: CheckoutAddonKind,
    requested: number | null,
    fallback: number | null
  ): number | null {
    if (requested == null) return fallback;
    const definition = checkoutAddonDefinitions(selectedPlan)[kind];
    if (!definition) return fallback;
    const option = definition.options.find((candidate) => {
      const candidateValue =
        kind === "devices"
          ? Number(candidate.total_units ?? candidate.extra_units ?? 0)
          : Number(candidate.total_units || 0);
      return Math.abs(candidateValue - requested) < 1e-9;
    });
    if (!option) return fallback;
    return kind === "devices" ? Number(option.extra_units || 0) : Number(option.total_units || 0);
  }

  function handleCheckoutSliderInteraction(active: boolean): void {
    if (checkoutSliderInteracting === active) return;
    checkoutSliderInteracting = active;
    if (active) {
      checkoutQuoteRequestId += 1;
      checkoutQuote = null;
      checkoutQuoteError = "";
      checkoutQuoteBusy = false;
    }
  }

  function checkoutPaymentOptions(): CheckoutPaymentOptions {
    return {
      balanceSource,
      checkoutAddons: checkoutAddonSelection,
      ...wataCheckout.wataSubscriptionContacts(selectedMethod, payerEmail, payerPhone),
    };
  }

  function checkoutQuotePlan(plan: PlanView | null): PlanView | null {
    const optimistic = planWithCheckoutSelection(plan);
    if (!optimistic || checkoutSliderInteracting || !checkoutQuote || checkoutQuoteError) {
      return optimistic;
    }
    return {
      ...optimistic,
      price: Number(checkoutQuote.effective_amount ?? optimistic.price ?? 0),
      stars_price:
        checkoutQuote.effective_stars == null
          ? optimistic.stars_price
          : Number(checkoutQuote.effective_stars),
    };
  }

  async function requestCheckoutQuote(
    requestId: number,
    body: PostPayload<"/api/subscription/quote">
  ): Promise<void> {
    try {
      const response = await api(buildSubscriptionQuotePath(), {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (requestId !== checkoutQuoteRequestId) return;
      checkoutQuote = response as Record<string, unknown>;
      checkoutQuoteError = "";
    } catch (error: unknown) {
      if (requestId !== checkoutQuoteRequestId) return;
      checkoutQuote = null;
      checkoutQuoteError = String((error as { message?: unknown })?.message || "quote_failed");
    } finally {
      if (requestId === checkoutQuoteRequestId) checkoutQuoteBusy = false;
    }
  }

  function applyPromoWithCheckoutAddons(): unknown {
    return applyCheckoutPromo({ checkoutAddons: checkoutAddonSelection });
  }
  function hwidRenewalFor(plan: PlanView | null) {
    return plan?.hwid_renewal?.available ? plan.hwid_renewal : null;
  }
  function isSubscriptionPlan(plan: PlanView | null) {
    const saleMode = String(plan?.sale_mode || "subscription").toLowerCase();
    return saleMode === "subscription";
  }
  function hwidRenewalAvailableForMethod(plan: PlanView | null) {
    const renewal = hwidRenewalFor(plan);
    if (
      providerManagesPrice() ||
      tributeShopSubscriptionSelected() ||
      !subscription?.active ||
      !isSubscriptionPlan(plan) ||
      !renewal
    ) {
      return false;
    }
    if (methodUsesStars()) return Number(renewal.stars_price || 0) > 0;
    return Number(renewal.price || 0) > 0;
  }
  function planWithSelectedHwidRenewal(plan: PlanView | null) {
    if (!plan || !renewHwidDevices || !hwidRenewalAvailableForMethod(plan)) return plan;
    const renewal = hwidRenewalFor(plan);
    if (!renewal) return plan;
    const withRenewal: PlanView = {
      ...plan,
      price: Number(plan.price || 0) + Number(renewal.price || 0),
    };
    if (Number(plan.stars_price || 0) > 0 && Number(renewal.stars_price || 0) > 0) {
      withRenewal.stars_price = Number(plan.stars_price || 0) + Number(renewal.stars_price || 0);
    }
    return withRenewal;
  }
  function planWithCheckoutSelection(plan: PlanView | null): PlanView | null {
    return planWithSelectedHwidRenewal(planWithSelectedCheckoutAddons(plan));
  }
  function paymentPriceLabel(plan: PlanView | null) {
    return priceLabelFn(planWithCheckoutSelection(plan), selectedMethod);
  }
  function checkoutPaymentPriceLabel(plan: PlanView | null) {
    if (providerManagesPrice()) return t("wa_price_managed_by_provider");
    const promoPrice = checkoutPromoPriceParts(plan);
    if (promoPrice) return promoPrice.discounted;
    if (checkoutPromoAppliedCode && checkoutPromoPriceText) return checkoutPromoPriceText;
    return paymentPriceLabel(plan);
  }
  function checkoutPromoDiscount() {
    return normalizedCheckoutPromoDiscount(checkoutPromoAppliedCode, checkoutPromoDiscountPercent);
  }
  function checkoutPromoAffectsPlan(plan: PlanView | null) {
    if (isTrialPaymentPlan(plan)) return false;
    return checkoutPromoAffectsQuotedPlan(
      checkoutPromoDiscount(),
      checkoutPromoMatchesPlan(
        plan,
        checkoutPromoAppliesTo,
        checkoutPromoMinSubscriptionDays,
        checkoutPromoMinTrafficGb
      ),
      true
    );
  }
  function discountedCheckoutPlan(plan: PlanView | null) {
    return discountedCheckoutPlanFn(plan, checkoutPromoDiscount());
  }
  function checkoutPromoPlanParts(plan: PlanView | null) {
    const checkoutPlan = planWithCheckoutSelection(plan);
    if (!checkoutPlan || !checkoutPromoAffectsPlan(plan)) return null;
    const discounted = discountedCheckoutPlan(checkoutPlan);
    if (!discounted) return null;
    return {
      base: checkoutPlan,
      discounted,
    };
  }
  function checkoutPromoPriceParts(plan: PlanView | null) {
    const promoPlans = checkoutPromoPlanParts(plan);
    if (!promoPlans) return null;
    return {
      base: priceLabelFn(promoPlans.base, selectedMethod),
      discounted: priceLabelFn(promoPlans.discounted, selectedMethod),
    };
  }
  const selectedPlanForPayment = $derived(planWithCheckoutSelection(selectedPlan));
  const selectedQuotedPlanForPayment = $derived(checkoutQuotePlan(selectedPlan));
  const paymentMethodAvailabilityPlan = $derived(
    checkoutPromoAffectsPlan(selectedPlan)
      ? discountedCheckoutPlan(selectedPlanForPayment)
      : selectedPlanForPayment
  );
  const paymentMethods = $derived(methodsForPlan(methods, paymentMethodAvailabilityPlan));
  const paymentMethodSelected = $derived(methodSelectable(paymentMethods, selectedMethod));

  $effect(() => {
    const definitions = checkoutAddonDefinitions(selectedPlan);
    const supported = (kind: CheckoutAddonKind, value: number | null) =>
      value === null ||
      Boolean(
        definitions[kind]?.options.some(
          (option) =>
            Math.abs(
              Number(kind === "devices" ? option.extra_units || 0 : option.total_units || 0) -
                Number(value)
            ) < 1e-9
        )
      );
    if (!supported("devices", checkoutDeviceCount) && checkoutDeviceCount !== 0) {
      checkoutDeviceCount = 0;
    }
    if (!supported("traffic", checkoutRegularLimitGb)) {
      const defaultRegularLimitGb = Number(definitions.traffic?.base_units || 0) || null;
      if (checkoutRegularLimitGb !== defaultRegularLimitGb)
        checkoutRegularLimitGb = defaultRegularLimitGb;
    }
    if (!supported("premium_traffic", checkoutPremiumLimitGb)) {
      const defaultPremiumLimitGb = Number(definitions.premium_traffic?.base_units || 0) || null;
      if (checkoutPremiumLimitGb !== defaultPremiumLimitGb) {
        checkoutPremiumLimitGb = defaultPremiumLimitGb;
      }
    }
    if (checkoutDeviceCount > 0 && renewHwidDevices) renewHwidDevices = false;
  });

  $effect(() => {
    if (!paymentModalOpen || paymentStep !== "checkout" || !selectedPlan) return;
    const firstMethod = firstAvailableMethod(paymentMethods);
    if (firstMethod && !methodSelectable(paymentMethods, selectedMethod)) {
      selectedMethod = firstMethod;
    }
  });
  $effect(() => {
    if (!paymentModalOpen || paymentStep !== "checkout" || !selectedPlan || !selectedMethod) {
      checkoutQuote = null;
      checkoutQuoteError = "";
      checkoutQuoteBusy = false;
      return;
    }
    if (isTrialPaymentPlan(selectedPlan)) {
      checkoutQuote = null;
      checkoutQuoteError = "";
      checkoutQuoteBusy = false;
      return;
    }
    if (checkoutSliderInteracting) {
      checkoutQuoteBusy = false;
      return;
    }
    const body = {
      gift,
      duration_days: selectedPlan.duration_days,
      months: selectedPlan.duration_days ? undefined : selectedPlan.months,
      traffic_gb: selectedPlan.traffic_gb,
      device_count: selectedPlan.device_count,
      tariff_key: selectedPlan.tariff_key,
      sale_mode: selectedPlan.sale_mode,
      method: selectedMethod,
      renew_hwid_devices:
        renewHwidDevices &&
        Boolean(selectedPlan?.hwid_renewal?.available) &&
        checkoutDeviceCount <= 0,
      checkout_addons: checkoutAddonSelection,
      promo_code: checkoutPromoAppliedCode || undefined,
    } as PostPayload<"/api/subscription/quote">;
    const requestId = ++checkoutQuoteRequestId;
    checkoutQuoteBusy = true;
    checkoutQuoteError = "";
    const timer = window.setTimeout(() => void requestCheckoutQuote(requestId, body), 90);
    return () => window.clearTimeout(timer);
  });
  $effect(() => {
    const identity = [
      planKeyFn(selectedPlan),
      selectedTariffKey || "legacy",
      checkoutAddonPreset?.deviceTotal ?? "",
      checkoutAddonPreset?.regularLimitGb ?? "",
      checkoutAddonPreset?.premiumLimitGb ?? "",
    ].join(":");
    if (identity !== checkoutPlanIdentity) {
      checkoutPlanIdentity = identity;
      const definitions = checkoutAddonDefinitions(selectedPlan);
      const defaultDevices = Number(definitions.devices?.initial_units || 0);
      const defaultRegular =
        Number(definitions.traffic?.initial_units ?? definitions.traffic?.base_units ?? 0) || null;
      const defaultPremium =
        Number(
          definitions.premium_traffic?.initial_units ?? definitions.premium_traffic?.base_units ?? 0
        ) || null;
      checkoutDeviceCount = Number(
        checkoutPresetValue("devices", checkoutAddonPreset?.deviceTotal ?? null, defaultDevices) ||
          0
      );
      checkoutRegularLimitGb = checkoutPresetValue(
        "traffic",
        checkoutAddonPreset?.regularLimitGb ?? null,
        defaultRegular
      );
      checkoutPremiumLimitGb = checkoutPresetValue(
        "premium_traffic",
        checkoutAddonPreset?.premiumLimitGb ?? null,
        defaultPremium
      );
    }
  });
  function hwidRenewalPriceLabel(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    if (!renewal) return "";
    return priceLabelFn(
      {
        price: renewal.price || 0,
        stars_price: renewal.stars_price,
        currency: renewal.currency || plan?.currency,
      },
      selectedMethod
    );
  }
  function showHwidRenewalBlock() {
    return checkoutDeviceCount <= 0 && hwidRenewalAvailableForMethod(selectedPlan);
  }
  function showHwidRenewalUnavailableNote() {
    return Boolean(
      subscription?.active &&
      Number(subscription?.extra_hwid_devices || 0) > 0 &&
      isSubscriptionPlan(selectedPlan) &&
      !showHwidRenewalBlock()
    );
  }
  function hwidRenewalCount(plan: PlanView | null = selectedPlan) {
    return Number(hwidRenewalFor(plan)?.device_count || subscription?.extra_hwid_devices || 0);
  }
  function hwidRenewalBonusLabel(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    const bonusGb = Number(renewal?.traffic_bonus_gb || 0);
    if (!(bonusGb > 0)) return "";
    return t("wa_hwid_devices_traffic_bonus", { gb: formatCompactNumber(bonusGb) });
  }
  function hwidRenewalHint(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    if (renewal?.valid_from_text && renewal?.valid_until_text) {
      return t("wa_hwid_devices_renewal_checkbox_hint", {
        from: renewal.valid_from_text,
        to: renewal.valid_until_text,
      });
    }
    return t("wa_hwid_devices_renewal_checkbox_hint_short");
  }
  function showHwidDesyncNotice() {
    return Boolean(
      subscription?.device_topup_renewal_available &&
      subscription?.extra_hwid_devices_valid_until_text
    );
  }
  const planKey = (plan: PlanView | null) => planKeyFn(plan);
  function planDisplayTitle(plan: PlanView | null) {
    return planDisplayTitleFn(plan, { trafficMode, t });
  }
  function planSubtitle(plan: PlanView | null) {
    return planSubtitleFn(plan, { t, termUnitLabel });
  }
  function planUnitHint(plan: PlanView | null) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function checkoutUnitPricePlan(plan: PlanView | null): PlanView | null {
    if (!planUnitHint(plan)) return null;
    const checkoutPlan =
      checkoutPromoPlanParts(plan)?.discounted || planWithCheckoutSelection(plan);
    if (!checkoutPlan) return null;
    const trafficUnit = trafficMode || !isSubscriptionPlan(plan);
    return checkoutUnitPrice(checkoutPlan, plan, trafficUnit, methodUsesStars());
  }
  function checkoutUnitPriceSuffix(plan: PlanView | null): string {
    const trafficUnit = trafficMode || !isSubscriptionPlan(plan);
    return t(trafficUnit ? "wa_per_gb_short" : "wa_per_month_label");
  }
  function tariffLimitLabel(tariff: TariffView) {
    return tariffLimitLabelFn(tariff, { t });
  }
  function checkoutPromoBlock() {
    return (
      !isTrialPaymentPlan(selectedPlan) &&
      checkoutPromoBlockVisible(
        providerManagesPrice(),
        Boolean(checkoutPromoAppliedCode || checkoutPromoStatus || selectedPlan)
      )
    );
  }
  function paymentTitle() {
    if (gift) return t("wa_gift_buy_title");
    if (isTrialPaymentPlan(selectedPlan)) return t("wa_trial_payment_title");
    if (singleTariffMode) {
      return selectedTariff?.billing_model === "traffic"
        ? t("wa_traffic_packages_title")
        : t("wa_subscription_title");
    }
    if (tariffMode) return t("wa_tariffs_title");
    return trafficMode ? t("wa_traffic_packages_title") : t("wa_subscription_title");
  }
  function paymentDescription() {
    if (gift) return "";
    if (isTrialPaymentPlan(selectedPlan)) return t("wa_trial_payment_description");
    if (tariffMode) {
      if (singleTariffMode) {
        return selectedTariff?.billing_model === "traffic"
          ? t("wa_traffic_packages_choose")
          : t("wa_subscription_choose_period");
      }
      return paymentStep === "checkout" && selectedTariff
        ? t("wa_tariff_choose_period_payment", { tariff: selectedTariff.title })
        : t("wa_tariffs_choose");
    }
    return trafficMode ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
  }
  function showSubscriptionPurchaseDescription() {
    if (isTrialPaymentPlan(selectedPlan)) return false;
    if (!subscriptionPurchaseDescription.trim() || trafficMode) return false;
    if (!tariffMode) return true;
    if (paymentStep === "tariff") return false;
    return String(selectedTariff?.billing_model || "period").toLowerCase() !== "traffic";
  }
  function showCompactSubscriptionHeader() {
    if (gift) return false;
    if (isTrialPaymentPlan(selectedPlan)) return false;
    if (trafficMode) return false;
    if (!tariffMode) return true;
    if (paymentStep === "tariff") return false;
    return String(selectedTariff?.billing_model || "period").toLowerCase() !== "traffic";
  }

  let balanceSource = $state<"user" | "partner" | null>(null);
  let partnerBalanceDiscount = $state(0);
  let payerEmail = $state("");
  let payerPhone = $state("");

  $effect(() => {
    if (wataCheckout.isWataSubscriptionMethod(selectedMethod)) {
      balanceSource = null;
      partnerBalanceDiscount = 0;
    }
    if (!paymentModalOpen) {
      payerEmail = "";
      payerPhone = "";
    }
  });

  function checkoutAmount(plan: PlanView | null) {
    const quotedAmount = Number(checkoutQuote?.effective_amount);
    if (checkoutQuote && Number.isFinite(quotedAmount) && quotedAmount >= 0) return quotedAmount;
    const quotedPromoAmount = Number(checkoutPromoEffectiveAmount || 0);
    if (checkoutPromoAppliedCode && quotedPromoAmount > 0) return quotedPromoAmount;
    return Number(checkoutQuotePlan(plan)?.price || 0);
  }

  function selectedMethodMinimum() {
    const method = methods.find(
      (item) => String(item.id || "").toLowerCase() === String(selectedMethod || "").toLowerCase()
    );
    return Math.max(
      0,
      Number(method?.minimum_amount || method?.min_amount || method?.shop_min_amount || 0)
    );
  }

  function partnerBalanceEligible() {
    return Boolean(
      selectedPlan &&
      !isTrialPaymentPlan(selectedPlan) &&
      selectedMethod &&
      checkoutAmount(selectedPlan) > 0 &&
      !methodUsesStars() &&
      !wataCheckout.isWataSubscriptionMethod(selectedMethod) &&
      !providerManagesPrice()
    );
  }

  const balancePreload = createCheckoutBalancePreload(
    () => api,
    () => paymentModalOpen,
    () => checkoutBalanceLookupPlan(selectedPlan, selectedTariffPlans, plans),
    () => {
      balanceSource = null;
      partnerBalanceDiscount = 0;
    }
  );

  function partnerCheckoutPriceParts(plan: PlanView | null) {
    if (!balanceSource || partnerBalanceDiscount <= 0 || !plan) return null;
    return {
      base: checkoutPaymentPriceLabel(plan),
      discounted: formatMoney(
        Math.max(0, checkoutAmount(plan) - partnerBalanceDiscount),
        String(plan.currency || "")
      ),
    };
  }
</script>

{#snippet checkoutTariffCard()}
  {#if selectedPlan && isSubscriptionPlan(selectedPlan)}
    <CheckoutAddonSliders
      addons={checkoutAddonDefinitions(selectedPlan)}
      selection={checkoutAddonSelection}
      plan={selectedPlan}
      tariffTitle={String(
        selectedTariff?.title || selectedPlan.tariff_name || selectedPlan.title || ""
      )}
      tariffDescription={String(selectedTariff?.description || selectedPlan.description || "")}
      method={selectedMethod}
      currency={String(selectedPlan.currency || "RUB")}
      disabled={checkoutAddonsUnavailableForMethod(selectedPlan)}
      animateValues={checkoutAddonValueAnimationEnabled}
      expandedByDefault={checkoutAddonEditorExpandedByDefault}
      {t}
      onChange={updateCheckoutAddon}
      onInteractionChange={handleCheckoutSliderInteraction}
    />
  {/if}
{/snippet}

{#snippet checkoutPaymentControls()}
  <CheckoutPaymentControls
    {api}
    {paymentModalOpen}
    partnerAmount={checkoutAmount(selectedPlan)}
    partnerCurrency={String(selectedPlan?.currency || "")}
    partnerEligible={partnerBalanceEligible()}
    partnerMinimum={selectedMethodMinimum()}
    prefetchedBalance={balancePreload.response}
    balancePreloadComplete={balancePreload.complete}
    bind:balanceSource
    bind:partnerBalanceDiscount
    hasMethods={Boolean(methods.length)}
    {paymentMethods}
    {selectedMethod}
    bind:payerEmail
    bind:payerPhone
    {paymentMethodsDisplayMode}
    {selectPaymentMethod}
    {checkoutQuoteError}
    showCheckoutPromo={checkoutPromoBlock()}
    {checkoutPromoInput}
    {checkoutPromoAppliedCode}
    {checkoutPromoIsError}
    {checkoutPromoStatus}
    applyCheckoutPromo={applyPromoWithCheckoutAddons}
    {clearCheckoutPromo}
    {setCheckoutPromoInput}
    payDisabled={!selectedPlan ||
      !paymentMethodSelected ||
      payBusy ||
      checkoutQuoteBusy ||
      Boolean(checkoutQuoteError) ||
      !wataCheckout.wataSubscriptionContactsValid(selectedMethod, payerEmail, payerPhone) ||
      (checkoutAddonsSelected() && checkoutAddonsUnavailableForMethod(selectedPlan))}
    createPayment={() => createPayment(checkoutPaymentOptions())}
    partnerPrice={partnerCheckoutPriceParts(selectedPlan)}
    promoPrice={checkoutPromoPlanParts(selectedPlan)}
    {selectedPlan}
    quotedPlan={selectedQuotedPlanForPayment}
    providerManagesPrice={providerManagesPrice()}
    fallbackPrice={selectedPlan ? checkoutPaymentPriceLabel(selectedPlan) : ""}
    priceUpdateIntervalMs={checkoutSliderInteracting ? 420 : 0}
    {t}
  />
{/snippet}

{#snippet paymentHeader()}
  <CheckoutHeader
    compact={showCompactSubscriptionHeader()}
    showPurchaseDescription={showSubscriptionPurchaseDescription()}
    title={paymentTitle()}
    description={paymentDescription()}
    purchaseDescription={subscriptionPurchaseDescription}
    {inline}
  />
{/snippet}

{#snippet paymentBody()}
  <div class="payment-dialog-body">
    {#if gift && paymentStep === "checkout"}{@render giftDelivery?.()}{/if}
    {#if pendingPayment}
      <PendingPaymentCard
        payment={pendingPayment}
        {payBusy}
        resume={resumePendingPayment}
        cancel={cancelPendingPayment}
        {t}
        {termUnitLabel}
      />
    {/if}
    {#if isTrialPaymentPlan(selectedPlan)}
      <TrialPaymentSummary plan={selectedPlan as PlanView} {t} />
      {@render checkoutPaymentControls()}
    {:else if tariffMode && !singleTariffMode && paymentStep === "tariff"}
      {#if tariffCatalog.length}
        <CheckoutTariffPicker
          tariffs={tariffCatalog}
          {selectedTariffKey}
          metaLabel={tariffLimitLabel}
          {selectTariff}
          {t}
        />
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={continueWithSelectedTariff}
          disabled={!selectedTariffKey}
        >
          {t("wa_next")}
          <ArrowRight size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else if tariffMode}
      {#if !singleTariffMode && !(subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key))}
        <button class="back-inline" type="button" onclick={backToTariffList}>
          <ArrowLeft size={16} />
          {t("wa_back_to_tariffs")}
        </button>
      {/if}
      {#if hasMultipleTariffs && selectedTariff}
        <p class="tariff-step-caption">
          {t("wa_selected_tariff", { tariff: selectedTariff.title })}
        </p>
      {/if}
      {#if selectedTariffPlans.length}
        {@render checkoutTariffCard()}
        {#if showHwidRenewalBlock()}
          <label class="hwid-renewal-option">
            <Checkbox
              checked={renewHwidDevices}
              ariaLabel={t("wa_hwid_devices_renewal_checkbox_aria")}
              onCheckedChange={(checked) => (renewHwidDevices = checked)}
            />
            <span>
              <strong>
                {t("wa_hwid_devices_renewal_checkbox", {
                  count: hwidRenewalCount(),
                  price: hwidRenewalPriceLabel(),
                })}
              </strong>
              <small>{hwidRenewalHint()}</small>
              {#if hwidRenewalBonusLabel()}
                <small class="hwid-traffic-bonus">{hwidRenewalBonusLabel()}</small>
              {/if}
              {#if showHwidDesyncNotice()}
                <small class="hwid-renewal-warning">
                  {t("wa_hwid_devices_desync_notice", {
                    date: subscription.extra_hwid_devices_valid_until_text,
                  })}
                </small>
              {/if}
            </span>
          </label>
        {:else if showHwidRenewalUnavailableNote()}
          <div class="subscription-purchase-description">
            <p>
              {t("wa_hwid_devices_renewal_unavailable", {
                count: Number(subscription.extra_hwid_devices || 0),
                date: subscription.extra_hwid_devices_valid_until_text || "",
              })}
            </p>
          </div>
        {/if}
        <div class="period-grid period-grid-two-columns">
          {#each selectedTariffPlans as plan}
            {@const promoPlans = checkoutPromoPlanParts(plan)}
            <button
              class:active={planKey(selectedPlan) === planKey(plan)}
              class="period-card"
              type="button"
              onclick={() => (selectedPlan = plan)}
            >
              <strong>{planSubtitle(plan) || planDisplayTitle(plan)}</strong>
              <CheckoutPeriodPrice
                plan={planWithCheckoutSelection(plan)}
                {promoPlans}
                unitPricePlan={checkoutUnitPricePlan(plan)}
                unitPriceSuffix={checkoutUnitPriceSuffix(plan)}
                method={selectedMethod}
                updateIntervalMs={checkoutSliderInteracting ? 420 : 0}
              />
              {#if planKey(selectedPlan) === planKey(plan)}
                <CheckCircle2 size={18} />
              {/if}
            </button>
          {/each}
        </div>
        {@render checkoutPaymentControls()}
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else}
      {@render checkoutTariffCard()}
      {#if showHwidRenewalBlock()}
        <label class="hwid-renewal-option">
          <Checkbox
            checked={renewHwidDevices}
            ariaLabel={t("wa_hwid_devices_renewal_checkbox_aria")}
            onCheckedChange={(checked) => (renewHwidDevices = checked)}
          />
          <span>
            <strong>
              {t("wa_hwid_devices_renewal_checkbox", {
                count: hwidRenewalCount(),
                price: hwidRenewalPriceLabel(),
              })}
            </strong>
            <small>{hwidRenewalHint()}</small>
            {#if hwidRenewalBonusLabel()}
              <small class="hwid-traffic-bonus">{hwidRenewalBonusLabel()}</small>
            {/if}
            {#if showHwidDesyncNotice()}
              <small class="hwid-renewal-warning">
                {t("wa_hwid_devices_desync_notice", {
                  date: subscription.extra_hwid_devices_valid_until_text,
                })}
              </small>
            {/if}
          </span>
        </label>
      {:else if showHwidRenewalUnavailableNote()}
        <div class="subscription-purchase-description">
          <p>
            {t("wa_hwid_devices_renewal_unavailable", {
              count: Number(subscription.extra_hwid_devices || 0),
              date: subscription.extra_hwid_devices_valid_until_text || "",
            })}
          </p>
        </div>
      {/if}
      <div class="period-grid period-grid-two-columns">
        {#each plans as plan}
          {@const promoPlans = checkoutPromoPlanParts(plan)}
          <button
            class:active={planKey(selectedPlan) === planKey(plan)}
            class="period-card"
            type="button"
            onclick={() => (selectedPlan = plan)}
          >
            <strong>{planDisplayTitle(plan)}</strong>
            {#if planSubtitle(plan)}
              <em>{planSubtitle(plan)}</em>
            {/if}
            <CheckoutPeriodPrice
              plan={planWithCheckoutSelection(plan)}
              {promoPlans}
              unitPricePlan={checkoutUnitPricePlan(plan)}
              unitPriceSuffix={checkoutUnitPriceSuffix(plan)}
              method={selectedMethod}
              updateIntervalMs={checkoutSliderInteracting ? 420 : 0}
            />
            {#if planKey(selectedPlan) === planKey(plan)}
              <CheckCircle2 size={18} />
            {/if}
          </button>
        {/each}
      </div>
      {@render checkoutPaymentControls()}
    {/if}
  </div>
{/snippet}

{#if inline}
  <section
    class="inline-payment-checkout"
    aria-label={showCompactSubscriptionHeader() ? t("wa_checkout_step_payment") : undefined}
    aria-labelledby={showCompactSubscriptionHeader() ? undefined : "payment-checkout-title"}
  >
    {@render paymentHeader()}
    {@render paymentBody()}
  </section>
{:else}
  <Dialog
    open={paymentModalOpen && balancePreload.ready}
    title={paymentTitle()}
    description={paymentDescription()}
    closeLabel={t("wa_close")}
    onclose={closePaymentModal}
    class={`payment-dialog-card webapp-payment-dialog${gift ? " gift-checkout-dialog" : ""}`}
    headerContent={paymentHeader}
  >
    {@render paymentBody()}
  </Dialog>
{/if}

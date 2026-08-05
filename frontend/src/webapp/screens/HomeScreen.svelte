<script lang="ts">
  import { onMount } from "svelte";
  import { slide } from "svelte/transition";
  import {
    CheckCircle2,
    CircleQuestionMark,
    CircleX,
    CreditCard,
    Database,
    Download,
    Gift,
    Repeat2,
    Send,
  } from "$components/ui/icons.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import TelegramNotificationsBanner from "../TelegramNotificationsBanner.svelte";
  import { LinearProgress } from "$components/patterns/webapp/index.js";
  import { formatTrafficGb } from "../../lib/webapp/formatters.js";
  import {
    trafficPercent as trafficPercentFn,
    trafficLabel as trafficLabelFn,
    trafficResetLabel as trafficResetLabelFn,
    trafficResetScheduled as trafficResetScheduledFn,
    trafficNextResetLabel as trafficNextResetLabelFn,
    regularTrafficLimitVisible as regularTrafficLimitVisibleFn,
    premiumTrafficPercent as premiumTrafficPercentFn,
    premiumTrafficLabel as premiumTrafficLabelFn,
    premiumNextResetLabel as premiumNextResetLabelFn,
    premiumTrafficLimitVisible as premiumTrafficLimitVisibleFn,
    premiumTitle as premiumTitleFn,
    premiumServerLabels as premiumServerLabelsFn,
    activeSubscriptionTermLabel as activeSubscriptionTermLabelFn,
  } from "../../lib/webapp/traffic.js";
  import type {
    AppSettings,
    BooleanAction,
    BrandConfig,
    ReferralState,
    SubscriptionView,
    TermUnitLabel,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  const SUBSCRIPTION_EXPIRY_WARNING_MS = 72 * 60 * 60 * 1000;
  const SUBSCRIPTION_EXPIRING_SOON_MS = 24 * 60 * 60 * 1000;
  const RESET_DETAIL_TRANSITION = { duration: 220 };
  const REGULAR_TRAFFIC_RESET_DETAIL_ID = "regular-traffic-reset-detail";
  const PREMIUM_TRAFFIC_RESET_DETAIL_ID = "premium-traffic-reset-detail";

  let {
    appSettings = {},
    brand = {},
    brandTitle = "",
    canChangeTariff = false,
    premiumTrafficTopupBarClickable = false,
    premiumTrafficTopupUnlocked = false,
    regularTrafficTopupBarClickable = false,
    regularTrafficTopupUnlocked = false,
    referral = {},
    currentTariffName = "",
    hasActiveTariffSubscription = false,
    hasMultipleTariffs = false,
    subscription = {},
    autoRenewBusy = false,
    linkTelegramBusy = false,
    telegramNotificationsNeedPrompt = false,
    telegramNotificationsStartLink = "",
    telegramNotificationsStatus = "unknown",
    trafficMode = false,
    trialBusy = false,
    termUnitLabel = () => "",
    activateTrial = () => {},
    toggleAutoRenew = () => {},
    linkTelegramAndActivateTrial = () => {},
    linkTelegramAndClaimReferralWelcome = () => {},
    openConnectLink = () => {},
    openPaymentModal = () => {},
    openTelegramNotificationsBot = () => {},
    openRegularTopupModal = () => {},
    openPremiumTopupModal = () => {},
    openTariffChangeModal = () => {},
    primaryPayActionLabel = () => "",
    t = (key) => key,
  }: {
    appSettings?: AppSettings;
    brand?: BrandConfig;
    brandTitle?: string;
    canChangeTariff?: boolean;
    premiumTrafficTopupBarClickable?: boolean;
    premiumTrafficTopupUnlocked?: boolean;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    referral?: ReferralState;
    currentTariffName?: string;
    hasActiveTariffSubscription?: boolean;
    hasMultipleTariffs?: boolean;
    subscription?: SubscriptionView;
    autoRenewBusy?: boolean;
    linkTelegramBusy?: boolean;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    trafficMode?: boolean;
    trialBusy?: boolean;
    termUnitLabel?: TermUnitLabel;
    activateTrial?: VoidAction;
    toggleAutoRenew?: BooleanAction;
    linkTelegramAndActivateTrial?: VoidAction;
    linkTelegramAndClaimReferralWelcome?: VoidAction;
    openConnectLink?: VoidAction;
    openPaymentModal?: VoidAction;
    openTelegramNotificationsBot?: VoidAction;
    openRegularTopupModal?: VoidAction;
    openPremiumTopupModal?: VoidAction;
    openTariffChangeModal?: VoidAction;
    primaryPayActionLabel?: () => string;
    t?: Translate;
  } = $props();

  let nowMs = $state(Date.now());
  let regularTrafficResetOpen = $state(false);
  let premiumTrafficResetOpen = $state(false);

  function trafficPercent(sub: SubscriptionView) {
    return trafficPercentFn(sub);
  }
  function trafficLabel(sub: SubscriptionView) {
    return trafficLabelFn(sub, t);
  }
  function trafficResetLabel(sub: SubscriptionView) {
    return trafficResetLabelFn(sub, t);
  }
  function trafficResetScheduled(sub: SubscriptionView = subscription) {
    return trafficResetScheduledFn(sub);
  }
  function trafficNextResetLabel(sub: SubscriptionView) {
    return trafficNextResetLabelFn(sub, t);
  }
  function regularTrafficLimitVisible(sub: SubscriptionView = subscription) {
    return regularTrafficLimitVisibleFn(sub);
  }
  function regularTrafficDepleted(sub: SubscriptionView = subscription) {
    const used = Number(sub?.traffic_used_bytes || 0);
    const limit = Number(sub?.traffic_limit_bytes || 0);
    return limit > 0 && used >= limit;
  }
  function regularTrafficCardClass(sub: SubscriptionView = subscription) {
    return [
      "traffic-card-compact",
      regularTrafficTopupBarClickable ? "traffic-card-clickable" : "",
      regularTrafficDepleted(sub) ? "traffic-card-depleted" : "",
    ]
      .filter(Boolean)
      .join(" ");
  }
  function premiumTrafficAvailable(sub: SubscriptionView = subscription) {
    return !regularTrafficDepleted(sub);
  }
  function premiumTrafficPercent(sub: SubscriptionView) {
    return premiumTrafficPercentFn(sub);
  }
  function premiumTrafficLimitVisible(sub: SubscriptionView = subscription) {
    return premiumTrafficLimitVisibleFn(sub);
  }
  function premiumTrafficLabel(sub: SubscriptionView) {
    return premiumTrafficLabelFn(sub, t);
  }
  function premiumNextResetLabel(sub: SubscriptionView) {
    return premiumNextResetLabelFn(sub, t);
  }
  function premiumTitle(sub: SubscriptionView = subscription) {
    return premiumTitleFn(sub, t);
  }
  function premiumTrafficMetaLabel(sub: SubscriptionView = subscription) {
    return sub?.premium_is_limited
      ? t("wa_premium_access_limited", {}, "Premium access is temporarily limited")
      : trafficResetLabel(sub);
  }
  function premiumServerLabels(sub: SubscriptionView) {
    return premiumServerLabelsFn(sub);
  }
  function activeSubscriptionTermLabel(sub: SubscriptionView) {
    return activeSubscriptionTermLabelFn(sub, { t, termUnitLabel });
  }
  function trialTrafficLabel() {
    const limit = Number(appSettings?.trial_traffic_limit_gb || 0);
    return limit > 0 ? formatTrafficGb(limit) : t("wa_unlimited_traffic");
  }
  function trialDurationLabel() {
    const days = Number(appSettings?.trial_duration_days || 0);
    return t("wa_sub_term_value_unit", {
      value: days,
      unit: termUnitLabel(days, "day"),
    });
  }
  function parseSubscriptionEndMs(sub: SubscriptionView) {
    const raw = String(sub?.end_date || "").trim();
    if (!raw) return null;
    const parsed = Date.parse(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  function dateOnlyFromEndText(text: unknown) {
    const value = String(text || "").trim();
    if (!value) return "";
    return value.split(/\s+/)[0] || value;
  }
  function dateOnlyFromIso(text: unknown) {
    const match = String(text || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[3]}.${match[2]}.${match[1]}` : "";
  }
  function subscriptionEndDateLabel(sub: SubscriptionView) {
    return dateOnlyFromEndText(sub?.end_date_text) || dateOnlyFromIso(sub?.end_date);
  }
  function formatSubscriptionCountdown(ms: number) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }

  const trialOfferAvailable = $derived(
    Boolean(!subscription?.active && appSettings?.trial_enabled && appSettings?.trial_available)
  );
  const trialRequiresTelegram = $derived(
    Boolean(
      !subscription?.active && appSettings?.trial_enabled && appSettings?.trial_requires_telegram
    )
  );
  const referralWelcomeRequiresTelegram = $derived(
    Boolean(
      !subscription?.active &&
      referral?.welcome_bonus_requires_telegram &&
      Number(referral?.welcome_bonus_days || 0) > 0
    )
  );
  const subscriptionEndMs = $derived(
    subscription?.active ? parseSubscriptionEndMs(subscription) : null
  );
  const subscriptionRemainingMs = $derived(Math.max(0, Number(subscriptionEndMs || 0) - nowMs));
  const subscriptionExpiryWarning = $derived(
    Boolean(
      subscription?.active &&
      subscriptionEndMs &&
      subscriptionRemainingMs > 0 &&
      subscriptionRemainingMs <= SUBSCRIPTION_EXPIRY_WARNING_MS
    )
  );
  const subscriptionEndDateText = $derived(subscriptionEndDateLabel(subscription));
  const subscriptionEndCountdown = $derived(formatSubscriptionCountdown(subscriptionRemainingMs));
  const subscriptionEndCountdownLabel = $derived(
    t(
      "wa_subscription_remaining_countdown",
      { countdown: subscriptionEndCountdown },
      `left: ${subscriptionEndCountdown}`
    )
  );
  const subscriptionExpiringSoon = $derived(
    Boolean(
      subscription?.active &&
      subscriptionEndMs &&
      subscriptionRemainingMs > 0 &&
      subscriptionRemainingMs < SUBSCRIPTION_EXPIRING_SOON_MS
    )
  );
  const subscriptionTermDisplayText = $derived(
    subscriptionExpiringSoon
      ? t("wa_subscription_expiring_soon", {}, "Ending soon!")
      : activeSubscriptionTermLabel(subscription)
  );
  const subscriptionEndDisplayText = $derived(
    subscriptionExpiryWarning
      ? `${subscriptionEndDateText || subscription.end_date_text} \u00b7 ${subscriptionEndCountdownLabel}`
      : subscriptionEndDateText
  );
  const statusCardClass = $derived(
    [
      "status-card",
      subscription.active ? "" : "status-card-inactive",
      subscriptionExpiryWarning ? "status-card-warning" : "",
    ]
      .filter(Boolean)
      .join(" ")
  );
  const autoRenewVisible = $derived(
    Boolean(subscription?.active && subscription?.auto_renew_available)
  );
  const autoRenewEnabled = $derived(Boolean(subscription?.auto_renew_enabled));

  onMount(() => {
    const countdownTimer = window.setInterval(() => {
      if (subscription?.active) nowMs = Date.now();
    }, 1000);

    return () => window.clearInterval(countdownTimer);
  });
</script>

<main class="home-layout">
  <div class="login-brand home-brand">
    <BrandMark {brand} size="xl" />
    <h1>{brandTitle}</h1>
  </div>

  {#if telegramNotificationsNeedPrompt}
    <TelegramNotificationsBanner
      startLink={telegramNotificationsStartLink}
      status={telegramNotificationsStatus}
      onOpenBot={openTelegramNotificationsBot}
      {t}
    />
  {/if}

  <div class="home-bottom">
    <Card class={statusCardClass}>
      {#if subscription.active}
        <div class="sub-status">
          <CheckCircle2 class="sub-status-icon" size={23} />
          <div class="sub-status-main">
            <h2>
              {trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")} | {subscriptionTermDisplayText}
            </h2>
            <div
              class:sub-status-details-with-tariff={hasActiveTariffSubscription &&
                hasMultipleTariffs &&
                currentTariffName}
              class="sub-status-details"
            >
              {#if hasActiveTariffSubscription && hasMultipleTariffs && currentTariffName}
                <p class="current-tariff-line">
                  {t("wa_current_tariff", { tariff: currentTariffName })}
                </p>
              {/if}
              <p class="subscription-end-line">
                {subscriptionEndDisplayText
                  ? t("wa_until_date", { date: subscriptionEndDisplayText })
                  : subscription.remaining_text}
              </p>
            </div>
          </div>
          {#if canChangeTariff}
            <Button
              data-webapp-action="open-tariff-change"
              class="status-tariff-action"
              variant="secondary"
              onclick={openTariffChangeModal}
            >
              <Repeat2 size={17} />
              {t("wa_change_tariff")}
            </Button>
          {/if}
        </div>
        {#if autoRenewVisible}
          <div class="auto-renew-row">
            <div class="auto-renew-state">
              <Repeat2 size={17} />
              <span>
                <strong>
                  {autoRenewEnabled ? t("wa_auto_renew_enabled") : t("wa_auto_renew_disabled")}
                </strong>
              </span>
            </div>
            <Button
              class="auto-renew-action"
              variant="secondary"
              onclick={() => toggleAutoRenew(!autoRenewEnabled)}
              disabled={autoRenewBusy ||
                (!autoRenewEnabled && !subscription?.auto_renew_can_enable)}
            >
              {#if autoRenewEnabled}
                <CircleX size={17} />
                {t("wa_auto_renew_disable")}
              {:else}
                <Repeat2 size={17} />
                {t("wa_auto_renew_enable")}
              {/if}
            </Button>
          </div>
        {/if}
      {:else}
        <div class="sub-status sub-status-inactive">
          <CircleX class="sub-status-icon" size={23} />
          <h2>{t("wa_home_subscription_inactive")}</h2>
        </div>
      {/if}
    </Card>

    {#if subscription.active}
      {#if regularTrafficLimitVisible(subscription)}
        <Card compact class={regularTrafficCardClass(subscription)}>
          {#if regularTrafficTopupBarClickable}
            <button
              data-webapp-action="open-regular-topup"
              class="card-click-target"
              type="button"
              onclick={openRegularTopupModal}
              aria-label={t("wa_add_traffic")}
            ></button>
          {/if}
          <div
            class="premium-server-dropdown premium-server-dropdown-inline traffic-reset-dropdown"
            data-open={regularTrafficResetOpen ? "true" : undefined}
          >
            <button
              class="traffic-summary-row premium-server-summary premium-server-trigger"
              type="button"
              aria-expanded={regularTrafficResetOpen}
              aria-controls={REGULAR_TRAFFIC_RESET_DETAIL_ID}
              onclick={() => {
                regularTrafficResetOpen = !regularTrafficResetOpen;
              }}
            >
              <span class="traffic-summary-left premium-summary-trigger">
                <span class="premium-summary-copy">
                  {t("wa_home_traffic_used")}
                  {#if trafficResetScheduled(subscription)}
                    <span class="traffic-summary-separator" aria-hidden="true">|</span>
                    {trafficResetLabel(subscription)}
                  {/if}
                </span>
                <CircleQuestionMark class="premium-server-help-icon" size={15} />
              </span>
              <strong class="traffic-summary-right">
                <span>{trafficLabel(subscription)}</span>
                <span class="traffic-summary-separator" aria-hidden="true">|</span>
                <span>{trafficPercent(subscription)}%</span>
              </strong>
            </button>
            {#if regularTrafficResetOpen}
              <div
                id={REGULAR_TRAFFIC_RESET_DETAIL_ID}
                class="premium-server-list premium-server-list-dropdown traffic-reset-detail"
                transition:slide={RESET_DETAIL_TRANSITION}
              >
                <div class="traffic-reset-detail-inner">
                  {#if trafficResetScheduled(subscription)}
                    <div class="traffic-reset-date-row">
                      <small>{t("wa_traffic_next_reset_label", {}, "Next reset")}</small>
                      <strong>{trafficNextResetLabel(subscription)}</strong>
                    </div>
                  {:else}
                    <div class="traffic-reset-date-row">
                      <small>{t("wa_traffic_reset_policy", {}, "Traffic reset policy")}</small>
                      <strong>{trafficResetLabel(subscription)}</strong>
                    </div>
                    <p class="traffic-reset-note">
                      {t(
                        "wa_traffic_reset_none_details",
                        {},
                        "Traffic does not reset automatically: available volume stays until you use it. If the tariff supports top-ups, you can add traffic with a separate package."
                      )}
                    </p>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
          <LinearProgress value={trafficPercent(subscription)} label={t("wa_home_traffic_used")} />
        </Card>
      {/if}
      {#if premiumTrafficAvailable(subscription) && premiumTrafficLimitVisible(subscription)}
        <Card
          compact
          class={`traffic-card-compact ${premiumTrafficTopupBarClickable ? "traffic-card-clickable " : ""}premium-traffic-card${subscription?.premium_is_limited ? " premium-traffic-card-limited" : ""}`}
        >
          {#if premiumTrafficTopupBarClickable}
            <button
              data-webapp-action="open-premium-topup"
              class="card-click-target"
              type="button"
              onclick={openPremiumTopupModal}
              aria-label={t("wa_add_traffic_premium", { target: premiumTitle(subscription) })}
            ></button>
          {/if}
          <div
            class="premium-server-dropdown premium-server-dropdown-inline traffic-reset-dropdown"
            data-open={premiumTrafficResetOpen ? "true" : undefined}
          >
            <button
              class="traffic-summary-row premium-server-summary premium-server-trigger"
              type="button"
              aria-expanded={premiumTrafficResetOpen}
              aria-controls={PREMIUM_TRAFFIC_RESET_DETAIL_ID}
              onclick={() => {
                premiumTrafficResetOpen = !premiumTrafficResetOpen;
              }}
            >
              <span class="traffic-summary-left premium-summary-trigger">
                <span class="premium-summary-copy">
                  {premiumTitle(subscription)}
                  <span class="traffic-summary-separator" aria-hidden="true">|</span>
                  {premiumTrafficMetaLabel(subscription)}
                </span>
                <CircleQuestionMark class="premium-server-help-icon" size={15} />
              </span>
              <strong class="traffic-summary-right">
                <span>{premiumTrafficLabel(subscription)}</span>
                <span class="traffic-summary-separator" aria-hidden="true">|</span>
                <span>{premiumTrafficPercent(subscription)}%</span>
              </strong>
            </button>
            {#if premiumTrafficResetOpen}
              <div
                id={PREMIUM_TRAFFIC_RESET_DETAIL_ID}
                class="premium-server-list premium-server-list-dropdown traffic-reset-detail"
                transition:slide={RESET_DETAIL_TRANSITION}
              >
                <div class="traffic-reset-detail-inner">
                  <div class="traffic-reset-date-row">
                    <small>{t("wa_traffic_next_reset_label", {}, "Next reset")}</small>
                    <strong>{premiumNextResetLabel(subscription)}</strong>
                  </div>
                  {#if premiumServerLabels(subscription).length}
                    <small>{t("wa_premium_servers_scope_label", {}, "Limit applies to")}</small>
                    <div>
                      {#each premiumServerLabels(subscription).slice(0, 8) as label}
                        <span>{label}</span>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
          <LinearProgress
            class="premium-progress"
            value={premiumTrafficPercent(subscription)}
            label={premiumTitle(subscription)}
          />
        </Card>
      {/if}
    {:else}
      {#if referralWelcomeRequiresTelegram}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>
                {t(
                  "wa_referral_welcome_telegram_required_title",
                  {},
                  "Your bonus is waiting for Telegram"
                )}
              </strong>
              <small>{t("wa_referral_program_title", {}, "Referral program")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_referral_welcome_telegram_required_description",
              { days: Number(referral?.welcome_bonus_days || 0) },
              "Link Telegram to claim {days} bonus days for registering via an invite."
            )}
          </p>
          <Button
            class="wide trial-card-action settings-telegram-link-btn attention-wrap"
            variant="telegram"
            onclick={linkTelegramAndClaimReferralWelcome}
            disabled={linkTelegramBusy}
          >
            <AttentionDot />
            <Send size={18} />
            {t("wa_referral_link_telegram_and_claim", {}, "Link and claim bonus")}
          </Button>
        </Card>
      {/if}

      {#if trialOfferAvailable}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>{t("wa_trial_offer_title", {}, "Start with a grace period")}</strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_offer_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "Activate a trial: {duration} of access and {traffic} available to download for free."
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "Duration")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "Available to download")}</small>
              <strong>{trialTrafficLabel()}</strong>
            </span>
          </div>
          <Button class="wide trial-card-action" onclick={activateTrial} disabled={trialBusy}>
            <Gift size={18} />
            {t("wa_trial_try_free", {}, "Try for free")}
          </Button>
        </Card>
      {:else if trialRequiresTelegram}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>
                {t("wa_trial_telegram_required_title", {}, "Link Telegram to start trial")}
              </strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_telegram_required_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "To activate a {duration} trial with {traffic}, link Telegram first."
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "Duration")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "Available to download")}</small>
              <strong>{trialTrafficLabel()}</strong>
            </span>
          </div>
          <Button
            class="wide trial-card-action settings-telegram-link-btn attention-wrap"
            variant="telegram"
            onclick={linkTelegramAndActivateTrial}
            disabled={linkTelegramBusy || trialBusy}
          >
            <AttentionDot />
            <Send size={18} />
            {t("wa_trial_link_telegram_and_activate", {}, "Link and activate")}
          </Button>
        </Card>
      {/if}
    {/if}

    <div class="action-stack">
      {#if subscription.active}
        <Button class="wide" onclick={openConnectLink}>
          <Download size={18} />
          {t("wa_install_and_configure")}
        </Button>
      {/if}
      <Button
        data-webapp-action="open-payment"
        class={`wide${subscription.active ? " subscription-renew-action" : ""}`}
        variant={subscription.active ? "secondary" : "default"}
        onclick={openPaymentModal}
      >
        {#if subscription.active}
          <CreditCard size={18} />
        {:else if trafficMode}
          <Database size={18} />
        {/if}
        {primaryPayActionLabel()}
      </Button>
      {#if regularTrafficTopupUnlocked && regularTrafficLimitVisible(subscription)}
        <Button
          data-webapp-action="open-regular-topup"
          class="wide"
          variant="secondary"
          onclick={openRegularTopupModal}
        >
          <Database size={18} />
          {t("wa_add_traffic")}
        </Button>
      {/if}
      {#if premiumTrafficTopupUnlocked && premiumTrafficAvailable(subscription) && premiumTrafficLimitVisible(subscription)}
        <Button
          data-webapp-action="open-premium-topup"
          class="wide"
          variant="secondary"
          onclick={openPremiumTopupModal}
        >
          <Database size={18} />
          {t("wa_add_traffic_premium", { target: premiumTitle(subscription) })}
        </Button>
      {/if}
    </div>
  </div>
</main>

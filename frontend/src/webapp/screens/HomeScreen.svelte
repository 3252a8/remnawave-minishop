<script lang="ts">
  import { onMount } from "svelte";
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
    regularTrafficLimitVisible as regularTrafficLimitVisibleFn,
    premiumTrafficPercent as premiumTrafficPercentFn,
    premiumTrafficLabel as premiumTrafficLabelFn,
    premiumTrafficLimitVisible as premiumTrafficLimitVisibleFn,
    premiumTitle as premiumTitleFn,
    premiumServerLabels as premiumServerLabelsFn,
    activeSubscriptionTermLabel as activeSubscriptionTermLabelFn,
  } from "../../lib/webapp/traffic.js";

  const SUBSCRIPTION_EXPIRY_WARNING_MS = 72 * 60 * 60 * 1000;
  const SUBSCRIPTION_EXPIRING_SOON_MS = 24 * 60 * 60 * 1000;

  type AnyRecord = Record<string, any>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

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
    appSettings?: AnyRecord;
    brand?: AnyRecord;
    brandTitle?: string;
    canChangeTariff?: boolean;
    premiumTrafficTopupBarClickable?: boolean;
    premiumTrafficTopupUnlocked?: boolean;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    referral?: AnyRecord;
    currentTariffName?: string;
    hasActiveTariffSubscription?: boolean;
    hasMultipleTariffs?: boolean;
    subscription?: AnyRecord;
    autoRenewBusy?: boolean;
    linkTelegramBusy?: boolean;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    trafficMode?: boolean;
    trialBusy?: boolean;
    termUnitLabel?: (value: number, unit: string) => string;
    activateTrial?: () => void;
    toggleAutoRenew?: (enabled: boolean) => void;
    linkTelegramAndActivateTrial?: () => void;
    linkTelegramAndClaimReferralWelcome?: () => void;
    openConnectLink?: () => void;
    openPaymentModal?: () => void;
    openTelegramNotificationsBot?: () => void;
    openRegularTopupModal?: () => void;
    openPremiumTopupModal?: () => void;
    openTariffChangeModal?: () => void;
    primaryPayActionLabel?: () => string;
    t?: Translate;
  } = $props();

  let nowMs = $state(Date.now());

  function trafficPercent(sub: AnyRecord) {
    return trafficPercentFn(sub);
  }
  function trafficLabel(sub: AnyRecord) {
    return trafficLabelFn(sub, t);
  }
  function trafficResetLabel(sub: AnyRecord) {
    return trafficResetLabelFn(sub, t);
  }
  function regularTrafficLimitVisible(sub: AnyRecord = subscription) {
    return regularTrafficLimitVisibleFn(sub);
  }
  function regularTrafficDepleted(sub: AnyRecord = subscription) {
    const used = Number(sub?.traffic_used_bytes || 0);
    const limit = Number(sub?.traffic_limit_bytes || 0);
    return limit > 0 && used >= limit;
  }
  function regularTrafficCardClass(sub: AnyRecord = subscription) {
    return [
      "traffic-card-compact",
      regularTrafficTopupBarClickable ? "traffic-card-clickable" : "",
      regularTrafficDepleted(sub) ? "traffic-card-depleted" : "",
    ]
      .filter(Boolean)
      .join(" ");
  }
  function regularTrafficMetaLabel(sub: AnyRecord = subscription) {
    return regularTrafficDepleted(sub) ? t("wa_traffic_depleted") : trafficResetLabel(sub);
  }
  function premiumTrafficAvailable(sub: AnyRecord = subscription) {
    return !regularTrafficDepleted(sub);
  }
  function premiumTrafficPercent(sub: AnyRecord) {
    return premiumTrafficPercentFn(sub);
  }
  function premiumTrafficLimitVisible(sub: AnyRecord = subscription) {
    return premiumTrafficLimitVisibleFn(sub);
  }
  function premiumTrafficLabel(sub: AnyRecord) {
    return premiumTrafficLabelFn(sub, t);
  }
  function premiumTitle(sub: AnyRecord = subscription) {
    return premiumTitleFn(sub, t);
  }
  function premiumTrafficMetaLabel(sub: AnyRecord = subscription) {
    return sub?.premium_is_limited
      ? t("wa_premium_access_limited", {}, "高级功能暂时受限")
      : t("wa_premium_reset_monthly", {}, "每月单独重置额度");
  }
  function premiumServerLabels(sub: AnyRecord) {
    return premiumServerLabelsFn(sub);
  }
  function activeSubscriptionTermLabel(sub: AnyRecord) {
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
  function parseSubscriptionEndMs(sub: AnyRecord) {
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
  function subscriptionEndDateLabel(sub: AnyRecord) {
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
      `剩余：${subscriptionEndCountdown}`
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
      ? t("wa_subscription_expiring_soon", {}, "即将到期")
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
  const homeBrandVisible = $derived(appSettings?.home_brand_visible !== false);
  const tariffChangeVisible = $derived(appSettings?.tariff_change_visible !== false);
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

<main class="home-layout" class:home-layout-compact={!homeBrandVisible}>
  {#if homeBrandVisible}
    <div class="login-brand home-brand">
      <BrandMark {brand} size="xl" />
      <h1>{brandTitle}</h1>
    </div>
  {/if}

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
          {#if canChangeTariff && tariffChangeVisible}
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
          <div class="traffic-summary-row">
            <span class="traffic-summary-left">
              {t("wa_home_traffic_used")}
              <span class="traffic-summary-separator" aria-hidden="true">|</span>
              {regularTrafficMetaLabel(subscription)}
            </span>
            <strong class="traffic-summary-right">
              <span>{trafficLabel(subscription)}</span>
              <span class="traffic-summary-separator" aria-hidden="true">|</span>
              <span>{trafficPercent(subscription)}%</span>
            </strong>
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
          {#if premiumServerLabels(subscription).length}
            <details class="premium-server-dropdown premium-server-dropdown-inline">
              <summary class="traffic-summary-row premium-server-summary">
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
              </summary>
              <div class="premium-server-list premium-server-list-dropdown">
                <div>
                  {#each premiumServerLabels(subscription).slice(0, 8) as label}
                    <span>{label}</span>
                  {/each}
                </div>
              </div>
            </details>
          {:else}
            <div class="traffic-summary-row">
              <span class="traffic-summary-left">
                {premiumTitle(subscription)}
                <span class="traffic-summary-separator" aria-hidden="true">|</span>
                {premiumTrafficMetaLabel(subscription)}
              </span>
              <strong class="traffic-summary-right">
                <span>{premiumTrafficLabel(subscription)}</span>
                <span class="traffic-summary-separator" aria-hidden="true">|</span>
                <span>{premiumTrafficPercent(subscription)}%</span>
              </strong>
            </div>
          {/if}
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
                {t("wa_referral_welcome_telegram_required_title", {}, "绑定 Telegram 后可获取奖励")}
              </strong>
              <small>{t("wa_referral_program_title", {}, "推荐奖励计划")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_referral_welcome_telegram_required_description",
              { days: Number(referral?.welcome_bonus_days || 0) },
              "绑定 Telegram 可获得 {days} 天邀请注册奖励。"
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
            {t("wa_referral_link_telegram_and_claim", {}, "绑定并领取奖励")}
          </Button>
        </Card>
      {/if}

      {#if trialOfferAvailable}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>{t("wa_trial_offer_title", {}, "先体验再支付")}</strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_offer_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "激活试用：{duration} 使用期限，赠送 {traffic} 下载流量。"
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "时长")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "可下载流量")}</small>
              <strong>{trialTrafficLabel()}</strong>
            </span>
          </div>
          <Button class="wide trial-card-action" onclick={activateTrial} disabled={trialBusy}>
            <Gift size={18} />
            {t("wa_trial_try_free", {}, "免费试用")}
          </Button>
        </Card>
      {:else if trialRequiresTelegram}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>
                {t("wa_trial_telegram_required_title", {}, "绑定 Telegram 后可开启试用")}
              </strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_telegram_required_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "先绑定 Telegram 后可激活 {duration} 试用，赠送 {traffic} 流量。"
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "时长")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "可下载流量")}</small>
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
            {t("wa_trial_link_telegram_and_activate", {}, "绑定并激活")}
          </Button>
        </Card>
      {/if}
    {/if}

    {#if !subscription.active}
      <Card compact class="purchase-journey-card">
        <div class="purchase-journey-item">
          <CreditCard size={18} />
          <span>
            <strong>{t("wa_purchase_step_payment", {}, "选择并支付")}</strong>
            <small>
              {t("wa_purchase_step_payment_hint", {}, "选择套餐和周期，完成支付。")}
            </small>
          </span>
        </div>
        <div class="purchase-journey-item">
          <Download size={18} />
          <span>
            <strong>{t("wa_purchase_step_import", {}, "导入订阅")}</strong>
            <small>
              {t("wa_purchase_step_import_hint", {}, "激活后，将订阅链接导入到你的客户端。")}
            </small>
          </span>
        </div>
      </Card>
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

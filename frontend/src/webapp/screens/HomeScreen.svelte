<script>
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
    premiumTrafficPercent as premiumTrafficPercentFn,
    premiumTrafficLabel as premiumTrafficLabelFn,
    premiumTitle as premiumTitleFn,
    premiumServerLabels as premiumServerLabelsFn,
    activeSubscriptionTermLabel as activeSubscriptionTermLabelFn,
  } from "../../lib/webapp/traffic.js";

  const SUBSCRIPTION_EXPIRY_WARNING_MS = 72 * 60 * 60 * 1000;
  const SUBSCRIPTION_EXPIRING_SOON_MS = 24 * 60 * 60 * 1000;

  export let appSettings = {};
  export let brand = {};
  export let brandTitle = "";
  export let canChangeTariff = false;
  export let premiumTrafficTopupBarClickable = false;
  export let premiumTrafficTopupUnlocked = false;
  export let regularTrafficTopupBarClickable = false;
  export let regularTrafficTopupUnlocked = false;
  export let referral = {};
  export let currentTariffName = "";
  export let hasActiveTariffSubscription = false;
  export let hasMultipleTariffs = false;
  export let subscription = {};
  export let linkTelegramBusy = false;
  export let telegramNotificationsNeedPrompt = false;
  export let telegramNotificationsStartLink = "";
  export let telegramNotificationsStatus = "unknown";
  export let trafficMode = false;
  export let trialBusy = false;
  export let termUnitLabel = () => ""; // We need this passed from App or context. Actually, App.svelte doesn't pass it yet. We'll pass it.

  let nowMs = Date.now();

  function trafficPercent(sub) {
    return trafficPercentFn(sub);
  }
  function trafficLabel(sub) {
    return trafficLabelFn(sub, t);
  }
  function trafficResetLabel(sub) {
    return trafficResetLabelFn(sub, t);
  }
  function regularTrafficDepleted(sub = subscription) {
    const used = Number(sub?.traffic_used_bytes || 0);
    const limit = Number(sub?.traffic_limit_bytes || 0);
    return limit > 0 && used >= limit;
  }
  function regularTrafficCardClass(sub = subscription) {
    return [
      "traffic-card-compact",
      regularTrafficTopupBarClickable ? "traffic-card-clickable" : "",
      regularTrafficDepleted(sub) ? "traffic-card-depleted" : "",
    ]
      .filter(Boolean)
      .join(" ");
  }
  function regularTrafficMetaLabel(sub = subscription) {
    return regularTrafficDepleted(sub) ? t("wa_traffic_depleted") : trafficResetLabel(sub);
  }
  function premiumTrafficAvailable(sub = subscription) {
    return !regularTrafficDepleted(sub);
  }
  function premiumTrafficPercent(sub) {
    return premiumTrafficPercentFn(sub);
  }
  function premiumTrafficLabel(sub) {
    return premiumTrafficLabelFn(sub, t);
  }
  function premiumTitle(sub = subscription) {
    return premiumTitleFn(sub, t);
  }
  function premiumTrafficMetaLabel(sub = subscription) {
    return sub?.premium_is_limited
      ? t("wa_premium_access_limited", {}, "Доступ к premium временно ограничен")
      : t("wa_premium_reset_monthly", {}, "Отдельный лимит на месяц");
  }
  function premiumServerLabels(sub) {
    return premiumServerLabelsFn(sub);
  }
  function activeSubscriptionTermLabel(sub) {
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
  function parseSubscriptionEndMs(sub) {
    const raw = String(sub?.end_date || "").trim();
    if (!raw) return null;
    const parsed = Date.parse(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  function dateOnlyFromEndText(text) {
    const value = String(text || "").trim();
    if (!value) return "";
    return value.split(/\s+/)[0] || value;
  }
  function dateOnlyFromIso(text) {
    const match = String(text || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[3]}.${match[2]}.${match[1]}` : "";
  }
  function subscriptionEndDateLabel(sub) {
    return dateOnlyFromEndText(sub?.end_date_text) || dateOnlyFromIso(sub?.end_date);
  }
  function formatSubscriptionCountdown(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const pad = (value) => String(value).padStart(2, "0");
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }

  $: trialOfferAvailable = Boolean(
    !subscription?.active && appSettings?.trial_enabled && appSettings?.trial_available
  );
  $: trialRequiresTelegram = Boolean(
    !subscription?.active && appSettings?.trial_enabled && appSettings?.trial_requires_telegram
  );
  $: referralWelcomeRequiresTelegram = Boolean(
    !subscription?.active &&
    referral?.welcome_bonus_requires_telegram &&
    Number(referral?.welcome_bonus_days || 0) > 0
  );
  $: subscriptionEndMs = subscription?.active ? parseSubscriptionEndMs(subscription) : null;
  $: subscriptionRemainingMs = Math.max(0, Number(subscriptionEndMs || 0) - nowMs);
  $: subscriptionExpiryWarning = Boolean(
    subscription?.active &&
    subscriptionEndMs &&
    subscriptionRemainingMs > 0 &&
    subscriptionRemainingMs <= SUBSCRIPTION_EXPIRY_WARNING_MS
  );
  $: subscriptionEndDateText = subscriptionEndDateLabel(subscription);
  $: subscriptionEndCountdown = formatSubscriptionCountdown(subscriptionRemainingMs);
  $: subscriptionEndCountdownLabel = t(
    "wa_subscription_remaining_countdown",
    { countdown: subscriptionEndCountdown },
    `осталось: ${subscriptionEndCountdown}`
  );
  $: subscriptionExpiringSoon = Boolean(
    subscription?.active &&
    subscriptionEndMs &&
    subscriptionRemainingMs > 0 &&
    subscriptionRemainingMs < SUBSCRIPTION_EXPIRING_SOON_MS
  );
  $: subscriptionTermDisplayText = subscriptionExpiringSoon
    ? t("wa_subscription_expiring_soon", {}, "Скоро закончится!")
    : activeSubscriptionTermLabel(subscription);
  $: subscriptionEndDisplayText = subscriptionExpiryWarning
    ? `${subscriptionEndDateText || subscription.end_date_text} \u00b7 ${subscriptionEndCountdownLabel}`
    : subscriptionEndDateText;
  $: statusCardClass = [
    "status-card",
    subscription.active ? "" : "status-card-inactive",
    subscriptionExpiryWarning ? "status-card-warning" : "",
  ]
    .filter(Boolean)
    .join(" ");

  onMount(() => {
    const countdownTimer = window.setInterval(() => {
      if (subscription?.active) nowMs = Date.now();
    }, 1000);

    return () => window.clearInterval(countdownTimer);
  });

  export let activateTrial = () => {};
  export let linkTelegramAndActivateTrial = () => {};
  export let linkTelegramAndClaimReferralWelcome = () => {};
  export let openConnectLink = () => {};
  export let openPaymentModal = () => {};
  export let openTelegramNotificationsBot = () => {};
  export let openRegularTopupModal = () => {};
  export let openPremiumTopupModal = () => {};
  export let openTariffChangeModal = () => {};
  export let primaryPayActionLabel = () => "";
  export let t = (key) => key;
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
              class="status-tariff-action"
              variant="secondary"
              onclick={openTariffChangeModal}
            >
              <Repeat2 size={17} />
              {t("wa_change_tariff")}
            </Button>
          {/if}
        </div>
      {:else}
        <div class="sub-status sub-status-inactive">
          <CircleX class="sub-status-icon" size={23} />
          <h2>{t("wa_home_subscription_inactive")}</h2>
        </div>
      {/if}
    </Card>

    {#if subscription.active}
      <Card compact class={regularTrafficCardClass(subscription)}>
        {#if regularTrafficTopupBarClickable}
          <button
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
      {#if premiumTrafficAvailable(subscription) && subscription?.premium_unlimited_override}
        <Card compact class="traffic-card-compact premium-traffic-card">
          {#if premiumServerLabels(subscription).length}
            <details class="premium-server-dropdown premium-server-dropdown-inline">
              <summary class="traffic-summary-row premium-server-summary">
                <span class="traffic-summary-left premium-summary-trigger">
                  <span class="premium-summary-copy">
                    {premiumTitle(subscription)}
                    <span class="traffic-summary-separator" aria-hidden="true">|</span>
                    {t("wa_premium_unlimited", {}, "Безлимит на premium-сервера")}
                  </span>
                  <CircleQuestionMark class="premium-server-help-icon" size={15} />
                </span>
                <strong class="traffic-summary-right">∞</strong>
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
                {t("wa_premium_unlimited", {}, "Безлимит на premium-сервера")}
              </span>
              <strong class="traffic-summary-right">∞</strong>
            </div>
          {/if}
        </Card>
      {:else if premiumTrafficAvailable(subscription) && Number(subscription?.premium_limit_bytes || 0) > 0}
        <Card
          compact
          class={`traffic-card-compact ${premiumTrafficTopupBarClickable ? "traffic-card-clickable " : ""}premium-traffic-card${subscription?.premium_is_limited ? " premium-traffic-card-limited" : ""}`}
        >
          {#if premiumTrafficTopupBarClickable}
            <button
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
                {t(
                  "wa_referral_welcome_telegram_required_title",
                  {},
                  "Бонус ждёт привязки Telegram"
                )}
              </strong>
              <small>{t("wa_referral_program_title", {}, "Реферальная программа")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_referral_welcome_telegram_required_description",
              { days: Number(referral?.welcome_bonus_days || 0) },
              "Привяжите Telegram, чтобы получить {days} бонусных дней за регистрацию по приглашению."
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
            {t("wa_referral_link_telegram_and_claim", {}, "Привязать и получить бонус")}
          </Button>
        </Card>
      {/if}

      {#if trialOfferAvailable}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>{t("wa_trial_offer_title", {}, "Можно начать с льготного периода")}</strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_offer_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "Активируйте триал: {duration} доступа и {traffic} для скачивания без оплаты."
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "Срок")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "Доступно для скачивания")}</small>
              <strong>{trialTrafficLabel()}</strong>
            </span>
          </div>
          <Button class="wide trial-card-action" onclick={activateTrial} disabled={trialBusy}>
            <Gift size={18} />
            {t("wa_trial_try_free", {}, "Попробовать бесплатно")}
          </Button>
        </Card>
      {:else if trialRequiresTelegram}
        <Card class="trial-card trial-offer-card">
          <div class="trial-card-head">
            <Gift size={22} />
            <span>
              <strong>
                {t("wa_trial_telegram_required_title", {}, "Привяжите Telegram для триала")}
              </strong>
              <small>{t("wa_trial_title")}</small>
            </span>
          </div>
          <p class="trial-card-description">
            {t(
              "wa_trial_telegram_required_description",
              { duration: trialDurationLabel(), traffic: trialTrafficLabel() },
              "Чтобы активировать триал на {duration} с лимитом {traffic}, сначала привяжите Telegram."
            )}
          </p>
          <div class="trial-card-facts">
            <span>
              <small>{t("wa_trial_duration_label", {}, "Срок")}</small>
              <strong>{trialDurationLabel()}</strong>
            </span>
            <span>
              <small>{t("wa_trial_download_traffic_label", {}, "Доступно для скачивания")}</small>
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
            {t("wa_trial_link_telegram_and_activate", {}, "Привязать и активировать")}
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
      {#if regularTrafficTopupUnlocked}
        <Button class="wide" variant="secondary" onclick={openRegularTopupModal}>
          <Database size={18} />
          {t("wa_add_traffic")}
        </Button>
      {/if}
      {#if premiumTrafficTopupUnlocked && premiumTrafficAvailable(subscription)}
        <Button class="wide" variant="secondary" onclick={openPremiumTopupModal}>
          <Database size={18} />
          {t("wa_add_traffic_premium", { target: premiumTitle(subscription) })}
        </Button>
      {/if}
    </div>
  </div>
</main>

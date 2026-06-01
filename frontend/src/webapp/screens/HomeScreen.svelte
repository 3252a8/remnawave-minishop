<script>
  import {
    CheckCircle2,
    CircleQuestionMark,
    CircleX,
    CreditCard,
    Database,
    Download,
    Gift,
    Repeat2,
  } from "$components/ui/icons.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
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

  export let appSettings = {};
  export let brand = {};
  export let brandTitle = "";
  export let canChangeTariff = false;
  export let premiumTrafficTopupBarClickable = false;
  export let premiumTrafficTopupUnlocked = false;
  export let regularTrafficTopupBarClickable = false;
  export let regularTrafficTopupUnlocked = false;
  export let currentTariffName = "";
  export let hasActiveTariffSubscription = false;
  export let hasMultipleTariffs = false;
  export let subscription = {};
  export let telegramNotificationsNeedPrompt = false;
  export let telegramNotificationsStartLink = "";
  export let telegramNotificationsStatus = "unknown";
  export let trafficMode = false;
  export let trialBusy = false;
  export let termUnitLabel = () => ""; // We need this passed from App or context. Actually, App.svelte doesn't pass it yet. We'll pass it.

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

  $: trialOfferAvailable = Boolean(
    !subscription?.active && appSettings?.trial_enabled && appSettings?.trial_available
  );

  export let activateTrial = () => {};
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
    <Card class={`status-card${subscription.active ? "" : " status-card-inactive"}`}>
      {#if subscription.active}
        <div class="sub-status">
          <CheckCircle2 class="sub-status-icon" size={23} />
          <div class="sub-status-main">
            <h2>
              {trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")} | {activeSubscriptionTermLabel(
                subscription
              )}
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
                {subscription.end_date_text
                  ? t("wa_until_date", { date: subscription.end_date_text })
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
    {:else if trialOfferAvailable}
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

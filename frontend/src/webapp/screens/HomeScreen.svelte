<script>
  import {
    CheckCircle2,
    ChevronsUpDown,
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
  function premiumTrafficPercent(sub) {
    return premiumTrafficPercentFn(sub);
  }
  function premiumTrafficLabel(sub) {
    return premiumTrafficLabelFn(sub, t);
  }
  function premiumTitle(sub = subscription) {
    return premiumTitleFn(sub, t);
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

  <div class="home-bottom">
    <Card class={`status-card${subscription.active ? "" : " status-card-inactive"}`}>
      {#if subscription.active}
        <div class="sub-status">
          <CheckCircle2 size={23} />
          <div>
            <h2>
              {trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")} | {activeSubscriptionTermLabel(
                subscription
              )}
            </h2>
            {#if hasActiveTariffSubscription && hasMultipleTariffs && currentTariffName}
              <p class="current-tariff-line">
                {t("wa_current_tariff", { tariff: currentTariffName })}
              </p>
            {/if}
            <p>
              {subscription.end_date_text
                ? t("wa_until_date", { date: subscription.end_date_text })
                : subscription.remaining_text}
            </p>
            {#if canChangeTariff}
              <Button
                class="wide status-tariff-action"
                variant="secondary"
                onclick={openTariffChangeModal}
              >
                <Repeat2 size={17} />
                {t("wa_change_tariff")}
              </Button>
            {/if}
          </div>
        </div>
      {:else}
        <div class="sub-status sub-status-inactive">
          <CircleX size={23} />
          <h2>{t("wa_home_subscription_inactive")}</h2>
        </div>
      {/if}
    </Card>

    {#if subscription.active}
      <Card class={regularTrafficTopupBarClickable ? "traffic-card-clickable" : ""}>
        {#if regularTrafficTopupBarClickable}
          <button
            class="card-click-target"
            type="button"
            onclick={openRegularTopupModal}
            aria-label={t("wa_add_traffic")}
          ></button>
        {/if}
        <div class="traffic-top">
          <span>{t("wa_home_traffic_used")}</span>
          <strong>{trafficLabel(subscription)}</strong>
        </div>
        <LinearProgress value={trafficPercent(subscription)} label={t("wa_home_traffic_used")} />
        <div class="traffic-meta">
          <span>{trafficResetLabel(subscription)}</span>
          <span class="traffic-percent">{trafficPercent(subscription)}%</span>
        </div>
      </Card>
      {#if subscription?.premium_unlimited_override}
        <Card class="premium-traffic-card">
          <div class="traffic-top">
            <span>{premiumTitle(subscription)}</span>
            <strong>∞</strong>
          </div>
          <div class="traffic-meta premium-traffic-meta">
            {#if premiumServerLabels(subscription).length}
              <details class="premium-server-dropdown">
                <summary>
                  <span>{t("wa_premium_unlimited", {}, "Безлимит на premium-сервера")}</span>
                  <ChevronsUpDown size={13} />
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
              <span>{t("wa_premium_unlimited", {}, "Безлимит на premium-сервера")}</span>
            {/if}
          </div>
        </Card>
      {:else if Number(subscription?.premium_limit_bytes || 0) > 0}
        <Card
          class={`${premiumTrafficTopupBarClickable ? "traffic-card-clickable " : ""}premium-traffic-card${subscription?.premium_is_limited ? " premium-traffic-card-limited" : ""}`}
        >
          {#if premiumTrafficTopupBarClickable}
            <button
              class="card-click-target"
              type="button"
              onclick={openPremiumTopupModal}
              aria-label={t("wa_add_traffic_premium", { target: premiumTitle(subscription) })}
            ></button>
          {/if}
          <div class="traffic-top">
            <span>{premiumTitle(subscription)}</span>
            <strong>{premiumTrafficLabel(subscription)}</strong>
          </div>
          <LinearProgress
            class="premium-progress"
            value={premiumTrafficPercent(subscription)}
            label={premiumTitle(subscription)}
          />
          <div class="traffic-meta premium-traffic-meta">
            {#if premiumServerLabels(subscription).length}
              <details class="premium-server-dropdown">
                <summary>
                  <span
                    >{subscription?.premium_is_limited
                      ? t("wa_premium_access_limited", {}, "Доступ к premium временно ограничен")
                      : t("wa_premium_reset_monthly", {}, "Отдельный лимит на месяц")}</span
                  >
                  <ChevronsUpDown size={13} />
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
              <span
                >{subscription?.premium_is_limited
                  ? t("wa_premium_access_limited", {}, "Доступ к premium временно ограничен")
                  : t("wa_premium_reset_monthly", {}, "Отдельный лимит на месяц")}</span
              >
            {/if}
            <span class="traffic-percent">{premiumTrafficPercent(subscription)}%</span>
          </div>
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
        class="wide"
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
      {#if premiumTrafficTopupUnlocked}
        <Button class="wide" variant="secondary" onclick={openPremiumTopupModal}>
          <Database size={18} />
          {t("wa_add_traffic_premium", { target: premiumTitle(subscription) })}
        </Button>
      {/if}
    </div>
  </div>
</main>

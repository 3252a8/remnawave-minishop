<script lang="ts">
  import { onMount } from "svelte";
  import {
    ArrowLeft,
    CheckCircle2,
    CircleX,
    Download,
    Gift,
    RefreshCw,
    Send,
  } from "$components/ui/icons.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { formatTrafficGb } from "../../lib/webapp/formatters.js";
  import type {
    AppSettings,
    BrandConfig,
    SubscriptionView,
    Translate,
    TrialActivationResult,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    appSettings?: AppSettings;
    brand?: BrandConfig;
    brandTitle?: string;
    subscription?: SubscriptionView;
    trialBusy?: boolean;
    linkTelegramBusy?: boolean;
    trialResult?: TrialActivationResult | null;
    trialError?: string;
    activateTrial?: VoidAction;
    linkTelegramAndActivateTrial?: VoidAction;
    openInstallOrConnect?: VoidAction;
    goHome?: VoidAction;
    t?: Translate;
  };

  let {
    appSettings = {},
    brand = {},
    brandTitle = "",
    subscription = {},
    trialBusy = false,
    linkTelegramBusy = false,
    trialResult = null,
    trialError = "",
    activateTrial = () => {},
    linkTelegramAndActivateTrial = () => {},
    openInstallOrConnect = () => {},
    goHome = () => {},
    t = (key, _params = {}, fallback = "") => fallback || key,
  }: Props = $props();

  let requested = false;

  const trialEnabled = $derived(Boolean(appSettings?.trial_enabled));
  const trialAvailable = $derived(Boolean(appSettings?.trial_available));
  const trialRequiresTelegram = $derived(
    Boolean(trialEnabled && appSettings?.trial_requires_telegram && !subscription?.active)
  );
  const canRequestTrial = $derived(
    Boolean(trialEnabled && trialAvailable && !subscription?.active)
  );
  const isTrialStatus = $derived(
    Boolean(trialResult?.activated) ||
      String(subscription?.status || "")
        .toUpperCase()
        .includes("TRIAL")
  );
  const hasActiveAccess = $derived(Boolean(subscription?.active || trialResult?.activated));
  const successTitle = $derived(
    isTrialStatus
      ? t("wa_trial_activated")
      : t("wa_home_subscription_active", {}, "Subscription active")
  );
  const endDateText = $derived(trialResult?.end_date_text || subscription?.end_date_text || "");
  const daysLeft = $derived(
    Number(trialResult?.days || subscription?.days_left || appSettings?.trial_duration_days || 0)
  );
  const trafficLabel = $derived(trialTrafficLabel());

  function trialTrafficLabel() {
    const resultTraffic = Number(trialResult?.traffic_gb || 0);
    const settingsTraffic = Number(appSettings?.trial_traffic_limit_gb || 0);
    const limit = resultTraffic || settingsTraffic;
    return limit > 0 ? formatTrafficGb(limit) : t("wa_unlimited_traffic");
  }

  onMount(() => {
    if (!requested && canRequestTrial) {
      requested = true;
      activateTrial();
    }
  });
</script>

<main class="trial-activation-screen">
  <div class="login-brand trial-activation-brand">
    <BrandMark {brand} size="lg" />
    <h1>{brandTitle}</h1>
  </div>

  <Card class="trial-activation-card">
    <div
      class={`trial-activation-icon ${
        trialBusy ? "trial-activation-icon-loading" : hasActiveAccess ? "is-success" : "is-muted"
      }`}
      aria-hidden="true"
    >
      {#if trialBusy}
        <RefreshCw size={27} />
      {:else if hasActiveAccess}
        <CheckCircle2 size={30} />
      {:else if trialRequiresTelegram}
        <Gift size={30} />
      {:else if trialError || !canRequestTrial}
        <CircleX size={30} />
      {:else}
        <Gift size={30} />
      {/if}
    </div>

    <div class="trial-activation-copy" aria-busy={trialBusy}>
      {#if trialBusy}
        <h2>{t("wa_trial_activation_loading", {}, "Activating trial...")}</h2>
        <p>{t("wa_trial_activation_wait", {}, "Preparing access and connection details.")}</p>
      {:else if hasActiveAccess}
        <h2>{successTitle}</h2>
        <p>
          {t(
            "wa_trial_active_hint",
            {},
            "Access is ready. Install the app and import the profile."
          )}
        </p>
        <dl class="trial-activation-facts">
          {#if endDateText}
            <div>
              <dt>{t("wa_trial_active_until_label", {}, "Active until")}</dt>
              <dd>{endDateText}</dd>
            </div>
          {/if}
          {#if daysLeft > 0}
            <div>
              <dt>{t("wa_trial_days_left_label", {}, "Time left")}</dt>
              <dd>{t("wa_trial_days_left", { days: daysLeft }, "{days} days")}</dd>
            </div>
          {/if}
          <div>
            <dt>{t("wa_trial_traffic_label", {}, "Traffic")}</dt>
            <dd>{trafficLabel}</dd>
          </div>
        </dl>
      {:else if trialRequiresTelegram}
        <h2>{t("wa_trial_telegram_required_title", {}, "Привяжите Telegram для триала")}</h2>
        <p>
          {t(
            "wa_trial_telegram_required_description",
            {
              duration:
                daysLeft > 0 ? t("wa_trial_days_left", { days: daysLeft }, "{days} days") : "",
              traffic: trafficLabel,
            },
            "Чтобы активировать пробный период, сначала привяжите Telegram."
          )}
        </p>
        <dl class="trial-activation-facts">
          {#if daysLeft > 0}
            <div>
              <dt>{t("wa_trial_duration_label", {}, "Срок")}</dt>
              <dd>{t("wa_trial_days_left", { days: daysLeft }, "{days} days")}</dd>
            </div>
          {/if}
          <div>
            <dt>{t("wa_trial_traffic_label", {}, "Traffic")}</dt>
            <dd>{trafficLabel}</dd>
          </div>
        </dl>
      {:else if trialError}
        <h2>{t("wa_trial_activation_failed")}</h2>
        <p>{trialError}</p>
      {:else}
        <h2>{t("wa_trial_unavailable_title", {}, "Trial is unavailable")}</h2>
        <p>
          {t(
            "wa_trial_unavailable_hint",
            {},
            "Trial may already be used, or this account already has active access."
          )}
        </p>
      {/if}
    </div>
  </Card>

  <div class="trial-activation-actions">
    {#if hasActiveAccess}
      <Button class="wide" onclick={openInstallOrConnect}>
        <Download size={18} />
        {t("wa_install_and_configure")}
      </Button>
    {:else if trialRequiresTelegram}
      <Button
        class="wide settings-telegram-link-btn attention-wrap"
        variant="telegram"
        onclick={linkTelegramAndActivateTrial}
        disabled={linkTelegramBusy || trialBusy}
      >
        <AttentionDot />
        <Send size={18} />
        {t("wa_trial_link_telegram_and_activate", {}, "Привязать и активировать")}
      </Button>
    {:else if trialError && canRequestTrial}
      <Button class="wide" onclick={activateTrial} disabled={trialBusy}>
        <RefreshCw size={18} />
        {t("wa_trial_retry", {}, "Try again")}
      </Button>
    {/if}
    <Button class="wide" variant="secondary" onclick={goHome}>
      <ArrowLeft size={18} />
      {t("wa_nav_home", {}, "Home")}
    </Button>
  </div>
</main>

<style>
  .trial-activation-screen {
    display: grid;
    min-height: calc(100dvh - 34px);
    align-content: center;
    gap: 18px;
    padding-bottom: 86px;
    animation: section-enter 0.22s ease-out both;
  }

  .trial-activation-brand {
    gap: 8px;
  }

  .trial-activation-brand h1 {
    font-size: 25px;
  }

  :global(.card.trial-activation-card) {
    display: grid;
    justify-items: center;
    gap: 14px;
    background: color-mix(in srgb, var(--accent) 6%, var(--panel));
    padding: 20px 16px 18px;
    text-align: center;
  }

  .trial-activation-icon {
    display: grid;
    width: 58px;
    height: 58px;
    place-items: center;
    border: 1px solid var(--surface-subtle-border);
    border-radius: 50%;
    color: var(--muted);
    background: color-mix(in srgb, var(--panel) 70%, transparent);
  }

  .trial-activation-icon.is-success {
    border-color: color-mix(in srgb, var(--accent) 52%, var(--border));
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 13%, var(--panel));
  }

  :global(.trial-activation-icon-loading svg) {
    animation: trial-spin 0.8s linear infinite;
  }

  .trial-activation-copy {
    display: grid;
    gap: 8px;
    width: 100%;
  }

  .trial-activation-copy h2,
  .trial-activation-copy p {
    margin: 0;
  }

  .trial-activation-copy h2 {
    color: var(--text);
    font-size: 19px;
    font-weight: 900;
    line-height: 1.15;
  }

  .trial-activation-copy p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.42;
  }

  .trial-activation-facts {
    display: grid;
    gap: 8px;
    width: 100%;
    margin: 8px 0 0;
  }

  .trial-activation-facts div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-width: 0;
    padding: 9px 10px;
    border: 1px solid var(--surface-subtle-border);
    border-radius: 12px;
    background: var(--surface-subtle);
    text-align: left;
  }

  .trial-activation-facts dt,
  .trial-activation-facts dd {
    min-width: 0;
    margin: 0;
    font-size: 12px;
    line-height: 1.2;
  }

  .trial-activation-facts dt {
    color: var(--muted);
  }

  .trial-activation-facts dd {
    overflow-wrap: anywhere;
    color: var(--text);
    font-weight: 850;
    text-align: right;
  }

  .trial-activation-actions {
    display: grid;
    gap: 10px;
  }

  @keyframes trial-spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>

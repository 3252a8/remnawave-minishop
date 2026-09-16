<script lang="ts">
  import {
    CheckCircle2,
    CircleQuestionMark,
    CircleX,
    Plus,
    Repeat2,
    TriangleAlert,
    WalletCards,
  } from "$components/ui/icons.js";
  import { fade } from "svelte/transition";

  import { LinearProgress } from "$components/patterns/webapp/index.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import { shouldShowUserBalance } from "$lib/webapp/balanceUiPolicy.js";
  import {
    premiumTitle as premiumTitleFn,
    premiumNextResetDate as premiumNextResetDateFn,
    premiumServerLabels as premiumServerLabelsFn,
    premiumTrafficLabel as premiumTrafficLabelFn,
    premiumTrafficLimitVisible as premiumTrafficLimitVisibleFn,
    premiumTrafficPercent as premiumTrafficPercentFn,
    premiumTrafficResetLabel as premiumTrafficResetLabelFn,
    regularTrafficLimitVisible as regularTrafficLimitVisibleFn,
    trafficLabel as trafficLabelFn,
    trafficNextResetDate as trafficNextResetDateFn,
    trafficPercent as trafficPercentFn,
    trafficResetLabel as trafficResetLabelFn,
  } from "$lib/webapp/traffic.js";
  import type {
    BalanceView,
    BooleanAction,
    SubscriptionView,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  let {
    balance = {} as BalanceView,
    subscription = {} as SubscriptionView,
    trafficMode = false,
    currentTariffName = "",
    hasActiveTariffSubscription = false,
    hasMultipleTariffs = false,
    canChangeTariff = false,
    subscriptionTermDisplayText = "",
    subscriptionEndDisplayText = "",
    subscriptionExpiryWarning = false,
    subscriptionExpired = false,
    autoRenewVisible = false,
    autoRenewEnabled = false,
    autoRenewBusy = false,
    regularTrafficTopupBarClickable = false,
    premiumTrafficTopupBarClickable = false,
    openBalanceTopup = () => {},
    openRegularTopupModal = () => {},
    openPremiumTopupModal = () => {},
    openTariffChangeModal = () => {},
    toggleAutoRenew = () => {},
    t = (key) => key,
  }: {
    balance?: BalanceView;
    subscription?: SubscriptionView;
    trafficMode?: boolean;
    currentTariffName?: string;
    hasActiveTariffSubscription?: boolean;
    hasMultipleTariffs?: boolean;
    canChangeTariff?: boolean;
    subscriptionTermDisplayText?: string;
    subscriptionEndDisplayText?: string;
    subscriptionExpiryWarning?: boolean;
    subscriptionExpired?: boolean;
    autoRenewVisible?: boolean;
    autoRenewEnabled?: boolean;
    autoRenewBusy?: boolean;
    regularTrafficTopupBarClickable?: boolean;
    premiumTrafficTopupBarClickable?: boolean;
    openBalanceTopup?: VoidAction;
    openRegularTopupModal?: VoidAction;
    openPremiumTopupModal?: VoidAction;
    openTariffChangeModal?: VoidAction;
    toggleAutoRenew?: BooleanAction;
    t?: Translate;
  } = $props();

  const PREMIUM_TRAFFIC_HELP_ID = "compact-premium-traffic-help";
  const HELP_TRANSITION = { duration: 120 };
  let premiumTrafficHelpOpen = $state(false);

  const regularTrafficVisible = $derived(
    Boolean(subscription.active && regularTrafficLimitVisibleFn(subscription))
  );
  const regularTrafficPercent = $derived(trafficPercentFn(subscription));
  const regularTrafficLabel = $derived(trafficLabelFn(subscription, t));
  const regularTrafficMeta = $derived(trafficResetLabelFn(subscription, t));
  const regularTrafficNextReset = $derived(trafficNextResetDateFn(subscription));
  const regularTrafficDepleted = $derived(
    Number(subscription?.traffic_limit_bytes || 0) > 0 &&
      Number(subscription?.traffic_used_bytes || 0) >=
        Number(subscription?.traffic_limit_bytes || 0)
  );
  const premiumTrafficVisible = $derived(
    Boolean(
      subscription.active && !regularTrafficDepleted && premiumTrafficLimitVisibleFn(subscription)
    )
  );
  const premiumTrafficPercent = $derived(premiumTrafficPercentFn(subscription));
  const premiumTrafficLabel = $derived(premiumTrafficLabelFn(subscription, t));
  const premiumTrafficTitle = $derived(premiumTitleFn(subscription, t));
  const premiumTrafficNextReset = $derived(premiumNextResetDateFn(subscription));
  const premiumServerLabels = $derived(premiumServerLabelsFn(subscription).slice(0, 8));
  const premiumServerDisplayLabels = $derived(
    premiumServerLabels.length ? premiumServerLabels : [premiumTrafficTitle]
  );
  const premiumTrafficMeta = $derived(
    subscription?.premium_is_limited
      ? t("wa_premium_access_limited", {}, "Premium access is temporarily limited")
      : premiumTrafficResetLabelFn(subscription, t)
  );
  const showTariff = $derived(
    Boolean(hasActiveTariffSubscription && hasMultipleTariffs && currentTariffName)
  );
  const summaryClass = $derived(
    [
      "home-compact-summary",
      subscription.active ? "" : "home-compact-summary-inactive",
      subscriptionExpiryWarning ? "home-compact-summary-warning" : "",
    ]
      .filter(Boolean)
      .join(" ")
  );

  function togglePremiumTrafficHelp(event: MouseEvent): void {
    event.stopPropagation();
    premiumTrafficHelpOpen = !premiumTrafficHelpOpen;
  }

  function closeTrafficHelpOnOutsideClick(event: MouseEvent): void {
    if (!premiumTrafficHelpOpen) return;

    const target = event.target;
    if (!(target instanceof Node)) {
      premiumTrafficHelpOpen = false;
      return;
    }

    if (document.getElementById(PREMIUM_TRAFFIC_HELP_ID)?.contains(target)) return;
    if (target instanceof Element && target.closest(".compact-traffic-help-trigger")) return;

    premiumTrafficHelpOpen = false;
  }
</script>

<svelte:window onclick={closeTrafficHelpOnOutsideClick} />

<Card class={summaryClass}>
  <div class="compact-summary-head">
    {#if subscriptionExpiryWarning}
      <TriangleAlert class="compact-status-icon" size={23} />
    {:else if subscription.active}
      <CheckCircle2 class="compact-status-icon" size={23} />
    {:else}
      <CircleX class="compact-status-icon" size={23} />
    {/if}

    <div class="compact-status-copy">
      <h2>
        {#if subscription.active}
          {#if subscriptionExpiryWarning}
            {subscriptionTermDisplayText}
          {:else}
            {trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")}
            {#if subscriptionTermDisplayText}
              <span class="meta-separator" aria-hidden="true"></span>
              {subscriptionTermDisplayText}
            {/if}
          {/if}
        {:else}
          {subscriptionExpired
            ? t("wa_home_subscription_expired")
            : t("wa_home_subscription_inactive")}
        {/if}
      </h2>
      {#if subscription.active}
        <p>
          {#if showTariff}
            <span>{t("wa_current_tariff", { tariff: currentTariffName })}</span>
            <span class="meta-separator" aria-hidden="true"></span>
          {/if}
          <span>
            {subscriptionEndDisplayText
              ? t("wa_until_date", { date: subscriptionEndDisplayText })
              : subscription.remaining_text}
          </span>
        </p>
      {:else if subscriptionExpired && subscriptionEndDisplayText}
        <p>{t("wa_subscription_expired_on", { date: subscriptionEndDisplayText })}</p>
      {/if}
    </div>

    {#if canChangeTariff || shouldShowUserBalance(balance)}
      <div class="compact-summary-head-actions">
        {#if canChangeTariff}
          <Button
            data-webapp-action="open-tariff-change"
            class="compact-tariff-action"
            size="sm"
            variant="secondary"
            onclick={openTariffChangeModal}
          >
            <Repeat2 size={15} />
            {t("wa_change_tariff")}
          </Button>
        {/if}
        {#if balance.enabled}
          <button
            data-webapp-action="open-balance-topup"
            type="button"
            class="compact-balance"
            onclick={openBalanceTopup}
            aria-label={t("wa_balance_topup_short", {}, "Top up")}
            title={t("wa_balance_topup_short", {}, "Top up")}
          >
            <WalletCards size={16} />
            <strong>{formatMoney(balance.amount, balance.currency)}</strong>
            <Plus size={14} />
          </button>
        {:else if shouldShowUserBalance(balance)}
          <span
            class="compact-balance compact-balance-readonly"
            aria-label={t("wa_balance_title", {}, "Balance")}
          >
            <WalletCards size={16} />
            <strong>{formatMoney(balance.amount, balance.currency)}</strong>
          </span>
        {/if}
      </div>
    {/if}
  </div>

  {#if regularTrafficVisible || premiumTrafficVisible}
    <div class="compact-traffic-grid">
      {#if regularTrafficVisible}
        <div class="compact-traffic-item">
          {#if regularTrafficTopupBarClickable}
            <button
              data-webapp-action="open-regular-topup"
              class="compact-traffic-click-target"
              type="button"
              onclick={openRegularTopupModal}
              aria-label={t("wa_add_traffic")}
            ></button>
          {/if}
          <div class="compact-traffic-label">
            <span>
              {t("wa_home_traffic_used")}
              <small>
                <span class="meta-separator" aria-hidden="true"></span>
                {regularTrafficMeta}
                {#if regularTrafficNextReset}<span class="meta-separator" aria-hidden="true"></span>
                  {regularTrafficNextReset}{/if}
              </small>
            </span>
            <strong
              >{regularTrafficLabel} <span class="meta-separator" aria-hidden="true"></span>
              {regularTrafficPercent}%</strong
            >
          </div>
          <LinearProgress value={regularTrafficPercent} label={t("wa_home_traffic_used")} />
        </div>
      {/if}

      {#if premiumTrafficVisible}
        <div class="compact-traffic-item">
          {#if premiumTrafficTopupBarClickable}
            <button
              data-webapp-action="open-premium-topup"
              class="compact-traffic-click-target"
              type="button"
              onclick={openPremiumTopupModal}
              aria-label={t("wa_add_traffic_premium", { target: premiumTrafficTitle })}
            ></button>
          {/if}
          <div class="compact-traffic-label">
            <span>
              {premiumTrafficTitle}
              <small>
                · {premiumTrafficMeta}
                {#if premiumTrafficNextReset}· {premiumTrafficNextReset}{/if}
              </small>
              <Button
                data-webapp-action="open-premium-traffic-help"
                class="compact-traffic-help-trigger"
                type="button"
                variant="ghost"
                size="icon"
                onclick={togglePremiumTrafficHelp}
                aria-expanded={premiumTrafficHelpOpen}
                aria-controls={PREMIUM_TRAFFIC_HELP_ID}
                aria-label={t("wa_premium_servers_scope_label", {}, "Limit applies to")}
              >
                <CircleQuestionMark class="compact-traffic-help-icon" size={12} />
              </Button>
            </span>
            <strong>{premiumTrafficLabel} · {premiumTrafficPercent}%</strong>
          </div>
          <LinearProgress
            class="premium-progress"
            value={premiumTrafficPercent}
            label={premiumTrafficTitle}
          />
          {#if premiumTrafficHelpOpen}
            <div
              id={PREMIUM_TRAFFIC_HELP_ID}
              class="compact-traffic-help compact-traffic-help-premium"
              role="dialog"
              aria-label={premiumTrafficTitle}
              transition:fade={HELP_TRANSITION}
            >
              <button
                class="compact-traffic-help-close"
                type="button"
                onclick={() => (premiumTrafficHelpOpen = false)}
                aria-label={t("wa_close")}
              >
                <CircleX size={14} />
              </button>
              <div class="compact-traffic-help-scope">
                <small>{t("wa_premium_servers_scope_label", {}, "Limit applies to")}</small>
                <div>
                  {#each premiumServerDisplayLabels as label}
                    <span>{label}</span>
                  {/each}
                </div>
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  {#if autoRenewVisible}
    <div class="compact-summary-actions">
      <Button
        size="sm"
        variant="secondary"
        onclick={() => toggleAutoRenew(!autoRenewEnabled)}
        disabled={autoRenewBusy || (!autoRenewEnabled && !subscription?.auto_renew_can_enable)}
      >
        {#if autoRenewEnabled}
          <CircleX size={15} />
          {t("wa_auto_renew_disable")}
        {:else}
          <Repeat2 size={15} />
          {t("wa_auto_renew_enable")}
        {/if}
      </Button>
    </div>
  {/if}
</Card>

<style>
  :global(section.home-compact-summary) {
    position: relative;
    z-index: 2;
    display: grid;
    gap: 11px;
    overflow: visible;
    padding: 12px;
  }
  :global(section.home-compact-summary-warning) {
    border-color: var(--warning-border);
    background:
      linear-gradient(
        135deg,
        color-mix(in srgb, var(--warning) 22%, var(--surface-sheen-soft)),
        color-mix(in srgb, var(--warning) 11%, var(--surface-sheen-soft))
      ),
      var(--panel);
    box-shadow:
      var(--shadow-soft),
      0 0 0 1px color-mix(in srgb, var(--warning) 16%, transparent),
      inset 0 1px 0 var(--inset-highlight);
  }
  :global(section.home-compact-summary-inactive) {
    border-color: color-mix(in srgb, var(--danger) 58%, var(--border));
    background:
      linear-gradient(
        135deg,
        color-mix(in srgb, var(--danger) 20%, var(--surface-sheen-soft)),
        color-mix(in srgb, var(--danger) 8%, var(--surface-sheen-soft))
      ),
      var(--panel);
  }
  .compact-summary-head {
    min-width: 0;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 9px;
  }
  .compact-summary-head-actions {
    min-width: 0;
    display: flex;
    align-items: stretch;
    justify-content: flex-end;
    gap: 7px;
  }
  :global(section.home-compact-summary .compact-summary-head-actions .compact-tariff-action) {
    min-height: 32px;
    padding: 5px 9px;
    font-size: 11px;
    white-space: nowrap;
  }
  :global(svg.compact-status-icon) {
    color: var(--accent);
  }
  :global(section.home-compact-summary-inactive svg.compact-status-icon) {
    color: var(--danger);
  }
  :global(section.home-compact-summary-warning svg.compact-status-icon) {
    color: var(--warning);
  }
  :global(section.home-compact-summary-warning .compact-status-copy h2),
  :global(section.home-compact-summary-warning .compact-status-copy p) {
    color: var(--warning-text);
  }
  :global(section.home-compact-summary-warning .compact-status-copy p) {
    font-variant-numeric: tabular-nums;
  }
  :global(section.home-compact-summary-inactive .compact-status-copy h2) {
    color: var(--danger);
  }
  .compact-status-copy {
    min-width: 0;
  }
  .compact-status-copy h2 {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin: 0;
    font-size: 14px;
    line-height: 1.25;
  }
  .compact-status-copy p {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin: 3px 0 0;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.25;
  }
  .compact-balance {
    position: relative;
    z-index: 1;
    min-height: 32px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 8px;
    border: 1px solid color-mix(in srgb, var(--accent) 48%, var(--border));
    border-radius: calc(var(--radius) - 2px);
    color: var(--text);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
    cursor: pointer;
    white-space: nowrap;
  }
  .compact-balance > :global(svg) {
    color: var(--accent);
  }
  .compact-balance strong {
    white-space: nowrap;
    font-size: 13px;
  }
  .compact-balance-readonly {
    cursor: default;
  }
  .compact-traffic-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    overflow: visible;
  }
  .compact-traffic-item {
    position: relative;
    min-width: 0;
    display: grid;
    gap: 0;
    padding: 0;
    border: 0;
    background: transparent;
  }
  .compact-traffic-item :global(.progress) {
    margin-top: 4px;
  }
  .compact-traffic-click-target {
    position: absolute;
    z-index: 2;
    inset: 0;
    border: 0;
    border-radius: inherit;
    background: transparent;
    cursor: pointer;
  }
  .compact-traffic-label {
    min-width: 0;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px;
    font-size: 11px;
  }
  .compact-traffic-label > span {
    min-width: 0;
    overflow: hidden;
    color: var(--muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .compact-traffic-label > span {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .compact-traffic-label small {
    font-size: inherit;
  }
  :global(section.home-compact-summary .compact-traffic-help-trigger.btn) {
    position: relative;
    z-index: 3;
    width: 18px;
    min-height: 18px;
    height: 18px;
    flex: 0 0 18px;
    padding: 0;
    color: var(--muted);
  }
  :global(svg.compact-traffic-help-icon) {
    flex: 0 0 auto;
    opacity: 0.72;
  }
  .compact-traffic-label strong {
    flex: 0 0 auto;
    font-size: 11px;
    white-space: nowrap;
  }
  .compact-traffic-help {
    position: absolute;
    z-index: 7;
    left: 8px;
    right: 8px;
    display: grid;
    gap: 8px;
    padding: 10px;
    border: 1px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: calc(var(--radius) - 1px);
    background: color-mix(in srgb, var(--panel) 96%, transparent);
    box-shadow: 0 12px 34px rgba(0, 0, 0, 0.42);
  }
  .compact-traffic-help-premium {
    bottom: calc(100% + 5px);
  }
  .compact-traffic-help-close {
    position: absolute;
    z-index: 1;
    top: 6px;
    right: 6px;
    width: 24px;
    height: 24px;
    display: inline-grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 50%;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .compact-traffic-help-close:hover {
    color: var(--text);
    background: var(--surface-hover);
  }
  .compact-traffic-help-scope > small {
    color: var(--muted);
    font-size: 10px;
  }
  .compact-traffic-help-scope {
    display: grid;
    gap: 5px;
  }
  .compact-traffic-help-scope > div {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .compact-traffic-help-scope span {
    padding: 2px 5px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    font-size: 9px;
    background: var(--surface-muted);
  }
  :global(section.home-compact-summary .compact-traffic-help .btn) {
    position: relative;
    z-index: 1;
    min-height: 30px;
    justify-self: start;
    padding: 5px 8px;
    font-size: 10px;
  }
  .compact-summary-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 7px;
    padding-top: 9px;
    border-top: 1px solid var(--border);
  }
  :global(section.home-compact-summary .compact-summary-actions .btn) {
    min-height: 31px;
    padding: 6px 9px;
    font-size: 11px;
  }
  @media (max-width: 520px) {
    :global(section.home-compact-summary) {
      gap: 9px;
      padding: 10px;
    }
    .compact-balance {
      min-height: 29px;
      padding: 4px 7px;
    }
    .compact-summary-head-actions {
      grid-column: 1 / -1;
      justify-content: stretch;
    }
    .compact-summary-head-actions .compact-balance,
    :global(section.home-compact-summary .compact-summary-head-actions .compact-tariff-action) {
      flex: 1 1 0;
      justify-content: center;
    }
    .compact-summary-actions {
      justify-content: stretch;
    }
    :global(section.home-compact-summary .compact-summary-actions .btn) {
      flex: 1 1 0;
    }
  }
</style>

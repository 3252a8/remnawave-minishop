<script lang="ts">
  import { ArrowRight, CalendarDays } from "$components/ui/icons.js";
  import {
    subscriptionDaysDisabledReason,
    subscriptionDaysQuoteUsable,
    type SubscriptionDaysQuote,
  } from "$lib/webapp/subscriptionDays.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    quote,
    devices = false,
    currentLang = "ru",
    t,
  }: {
    quote: SubscriptionDaysQuote;
    devices?: boolean;
    currentLang?: string;
    t: Translate;
  } = $props();

  const usable = $derived(subscriptionDaysQuoteUsable(quote));
  function date(value: string | null): string {
    if (!value) return "—";
    return new Intl.DateTimeFormat(currentLang, {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }
</script>

<div class="subscription-days-quote" class:unavailable={!usable} role="status">
  <div class="subscription-days-heading">
    <CalendarDays size={18} />
    <strong
      >{usable
        ? t("wa_subscription_days_charge", { days: quote.days_to_charge })
        : t("wa_subscription_days_method")}</strong
    >
  </div>
  {#if usable}
    <div class="subscription-days-expiry">
      <span>{t("wa_subscription_days_expiry")}</span>
      <div class="subscription-days-dates">
        <s>{date(quote.current_expires_at)}</s>
        <ArrowRight size={14} aria-hidden="true" />
        <strong>{date(quote.next_expires_at)}</strong>
      </div>
    </div>
    <p>{t(devices ? "wa_subscription_days_devices_hint" : "wa_subscription_days_hint")}</p>
  {:else}
    <p>{subscriptionDaysDisabledReason(quote, t)}</p>
  {/if}
</div>

<style>
  .subscription-days-quote {
    display: grid;
    gap: 8px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-control);
    background: var(--panel-2);
    color: var(--text);
    min-width: 0;
  }
  .subscription-days-heading {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .subscription-days-heading :global(svg) {
    flex-shrink: 0;
    color: var(--accent);
  }
  .subscription-days-expiry {
    display: grid;
    gap: 4px;
    font-size: 12px;
  }
  .subscription-days-expiry > span,
  .subscription-days-dates s,
  p {
    color: var(--muted);
  }
  .subscription-days-dates {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
  }
  .subscription-days-dates strong,
  .subscription-days-dates s {
    overflow-wrap: anywhere;
  }
  p {
    margin: 0;
    font-size: 12px;
    line-height: 1.45;
  }
  .unavailable {
    background: transparent;
  }
</style>

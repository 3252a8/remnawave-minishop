<script lang="ts">
  import { ArrowDownUp, SatelliteDish, Smartphone } from "$components/ui/icons.js";
  import Badge from "$components/ui/badge.svelte";
  import type { TariffLimitFact } from "$lib/webapp/tariffs.js";
  import type { Translate } from "$lib/webapp/types.js";
  import AnimatedNumber from "./AnimatedNumber.svelte";

  let {
    facts,
    compact = false,
    inline = false,
    animateValues = false,
    updateIntervalMs = 0,
    t = (key) => key,
  }: {
    facts: TariffLimitFact[];
    compact?: boolean;
    inline?: boolean;
    animateValues?: boolean;
    updateIntervalMs?: number;
    t?: Translate;
  } = $props();

  function valueLabel(fact: TariffLimitFact): string {
    if (fact.unavailable) return t("wa_checkout_tariff_not_included", {}, "Not included");
    if (!fact.known) return t("wa_checkout_tariff_not_specified", {}, "Not specified");
    if (fact.unlimited) return t("wa_checkout_tariff_unlimited", {}, "Unlimited");
    return fact.valueText || `${fact.units}${fact.kind === "devices" ? "" : " GB"}`;
  }
</script>

{#snippet factValue(fact: TariffLimitFact)}
  <span class="checkout-addon-value" aria-hidden={compact ? true : undefined}>
    {#if fact.unavailable}
      <span class="checkout-addon-state">
        {compact ? "—" : valueLabel(fact)}
      </span>
    {:else if !fact.known}
      <span class="checkout-addon-state">
        {compact ? "?" : valueLabel(fact)}
      </span>
    {:else if fact.unlimited}
      <span class="checkout-addon-unlimited checkout-addon-state">
        {compact ? "∞" : valueLabel(fact)}
      </span>
    {:else if fact.valueText}
      <span class="checkout-addon-state">{fact.valueText}</span>
    {:else}
      <AnimatedNumber
        value={fact.units}
        suffix={fact.kind === "devices" ? "" : " GB"}
        ariaLabel={valueLabel(fact)}
        format={{ maximumFractionDigits: 2 }}
        animated={animateValues}
        {updateIntervalMs}
      />
    {/if}
  </span>
{/snippet}

{#snippet factLabel(fact: TariffLimitFact)}
  <span class="checkout-tariff-fact-label" aria-hidden={compact ? true : undefined}>
    <span class="checkout-tariff-limit-icon" aria-hidden="true">
      {#if fact.kind === "devices"}
        <Smartphone size={13} strokeWidth={2} />
      {:else if fact.kind === "traffic"}
        <ArrowDownUp size={13} strokeWidth={2} />
      {:else}
        <SatelliteDish size={13} strokeWidth={2} />
      {/if}
    </span>
    <span class="checkout-addon-label">{fact.label}</span>
  </span>
{/snippet}

<div
  class:is-compact={compact}
  class:is-inline={compact && inline}
  class="checkout-tariff-facts tariff-limit-facts"
>
  {#each facts as fact (fact.kind)}
    {#if compact}
      <Badge
        variant="outline"
        class={`checkout-tariff-fact tariff-limit-badge${fact.adjustable ? " adjustable" : ""}`}
        role="img"
        aria-label={`${fact.label}: ${valueLabel(fact)}`}
        title={`${fact.label}: ${valueLabel(fact)}`}
      >
        {@render factLabel(fact)}
        {@render factValue(fact)}
      </Badge>
    {:else}
      <div class:adjustable={Boolean(fact.adjustable)} class="checkout-tariff-fact">
        {@render factValue(fact)}
        {@render factLabel(fact)}
      </div>
    {/if}
  {/each}
</div>

<style>
  :global(.checkout-tariff-facts):where(.tariff-limit-facts:not(.is-compact)) {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    min-width: 0;
    width: 100%;
  }

  :where(.tariff-limit-facts:not(.is-compact)) :global(.checkout-tariff-fact) {
    display: flex;
    flex-direction: column;
    min-width: 0;
    align-items: flex-start;
    justify-content: space-between;
    gap: 3px;
    padding: 0 8px;
  }

  :where(.tariff-limit-facts:not(.is-compact))
    :global(.checkout-tariff-fact + .checkout-tariff-fact) {
    border-left: 1px solid var(--border);
  }

  :where(.tariff-limit-facts) :global(.checkout-tariff-fact-label) {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 5px;
  }

  :where(.tariff-limit-facts) :global(.checkout-tariff-fact .checkout-tariff-limit-icon) {
    display: inline-grid;
    width: 14px;
    height: 14px;
    flex: 0 0 auto;
    place-items: center;
    color: var(--muted);
  }

  :where(.tariff-limit-facts) :global(.checkout-addon-label) {
    color: var(--text);
    font-size: 11px;
    font-weight: 400;
    line-height: 1.15;
    overflow-wrap: anywhere;
  }

  :where(.tariff-limit-facts) :global(.checkout-addon-value) {
    min-width: 0;
    color: var(--text);
    font-size: 15px;
    font-variant-numeric: tabular-nums;
    font-weight: 900;
    letter-spacing: -0.035em;
    overflow-wrap: anywhere;
  }

  :where(.tariff-limit-facts) :global(.checkout-addon-state) {
    font-size: 12px;
    letter-spacing: -0.015em;
    line-height: 1.25;
  }

  @media (max-width: 520px) {
    :global(.checkout-tariff-facts):where(.tariff-limit-facts:not(.is-compact)) {
      grid-template-columns: minmax(0, 1fr);
    }

    :where(.tariff-limit-facts:not(.is-compact)) :global(.checkout-tariff-fact) {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, auto);
      align-items: center;
      gap: 10px;
      padding: 5px 11px 5px 6px;
    }

    :where(.tariff-limit-facts:not(.is-compact))
      :global(.checkout-tariff-fact + .checkout-tariff-fact) {
      border-top: 1px solid var(--border);
      border-left: 0;
    }

    :where(.tariff-limit-facts:not(.is-compact))
      :global(.checkout-tariff-fact .checkout-addon-value) {
      grid-column: 2;
      grid-row: 1;
      justify-self: end;
      text-align: right;
    }

    :where(.tariff-limit-facts:not(.is-compact)) :global(.checkout-tariff-fact-label) {
      grid-column: 1;
      grid-row: 1;
    }
  }

  :global(.checkout-tariff-facts):where(.tariff-limit-facts.is-compact) {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    min-width: 0;
    width: 100%;
  }

  :where(.tariff-limit-facts.is-compact) :global(.tariff-limit-badge) {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 26px;
    min-width: 0;
    max-width: 100%;
    padding: 4px 8px;
    border: 1px solid var(--border);
    background: var(--surface-muted);
    color: var(--text);
  }

  :where(.tariff-limit-facts.is-compact) :global(.checkout-addon-value),
  :where(.tariff-limit-facts.is-compact) :global(.checkout-addon-state) {
    font-size: 11px;
    font-weight: 650;
    line-height: 1;
    letter-spacing: 0;
    white-space: nowrap;
  }

  :where(.tariff-limit-facts.is-compact) :global(.checkout-addon-label) {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  :global(.checkout-tariff-facts):where(.tariff-limit-facts.is-compact.is-inline) {
    flex: 0 1 auto;
    gap: 4px;
    width: auto;
    max-width: 100%;
  }

  :where(.tariff-limit-facts.is-compact.is-inline) :global(.tariff-limit-badge) {
    gap: 3px;
    min-height: 24px;
    padding: 3px 5px;
  }

  :where(.tariff-limit-facts.is-compact.is-inline) :global(.checkout-addon-state) {
    white-space: normal;
    overflow-wrap: anywhere;
  }
</style>

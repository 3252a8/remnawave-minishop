<script module lang="ts">
  import type { PlanView } from "$lib/webapp/types.js";

  export type CheckoutPeriodOption = {
    key: string | number;
    plan: PlanView;
    title: string;
    subtitle: string;
    checkoutPlan: PlanView | null;
    promoPlans: { base: PlanView; discounted: PlanView } | null;
    unitPricePlan: PlanView | null;
    unitPriceSuffix: string;
  };

  export type CheckoutRenewalOption = {
    label: string;
    hint: string;
    bonusLabel: string;
    warning: string;
  };
</script>

<script lang="ts">
  import { CheckCircle2 } from "$components/ui/icons.js";
  import Checkbox from "$components/ui/checkbox.svelte";
  import CheckoutPeriodPrice from "./CheckoutPeriodPrice.svelte";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    options = [],
    selectedKey = "",
    renewalOption = null,
    renewalUnavailableNote = "",
    renewHwidDevices = $bindable(true),
    animated = true,
    method = "",
    updateIntervalMs = 0,
    onSelect = () => {},
    t = (key) => key,
  }: {
    options?: CheckoutPeriodOption[];
    selectedKey?: string | number;
    renewalOption?: CheckoutRenewalOption | null;
    renewalUnavailableNote?: string;
    renewHwidDevices?: boolean;
    animated?: boolean;
    method?: string;
    updateIntervalMs?: number;
    onSelect?: (plan: PlanView) => void;
    t?: Translate;
  } = $props();
</script>

{#if renewalOption}
  <label class="hwid-renewal-option">
    <Checkbox
      checked={renewHwidDevices}
      ariaLabel={t("wa_hwid_devices_renewal_checkbox_aria")}
      onCheckedChange={(checked) => (renewHwidDevices = checked)}
    />
    <span>
      <strong>{renewalOption.label}</strong>
      <small>{renewalOption.hint}</small>
      {#if renewalOption.bonusLabel}
        <small class="hwid-traffic-bonus">{renewalOption.bonusLabel}</small>
      {/if}
      {#if renewalOption.warning}
        <small class="hwid-renewal-warning">{renewalOption.warning}</small>
      {/if}
    </span>
  </label>
{:else if renewalUnavailableNote}
  <div class="subscription-purchase-description">
    <p>{renewalUnavailableNote}</p>
  </div>
{/if}
<div class="period-grid period-grid-two-columns">
  {#each options as option (option.key)}
    <button
      class:active={selectedKey === option.key}
      class="period-card"
      type="button"
      onclick={() => onSelect(option.plan)}
    >
      <strong>{option.title}</strong>
      {#if option.subtitle}
        <em>{option.subtitle}</em>
      {/if}
      <CheckoutPeriodPrice
        plan={option.checkoutPlan}
        promoPlans={option.promoPlans}
        unitPricePlan={option.unitPricePlan}
        unitPriceSuffix={option.unitPriceSuffix}
        {method}
        {animated}
        {updateIntervalMs}
      />
      {#if selectedKey === option.key}
        <CheckCircle2 size={18} />
      {/if}
    </button>
  {/each}
</div>

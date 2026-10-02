<script lang="ts">
  import { AnimatedPrice } from "$components/patterns/webapp/index.js";
  import type { PlanView } from "$lib/webapp/types.js";

  let {
    plan = null,
    promoPlans = null,
    unitPricePlan = null,
    unitPriceSuffix = "",
    method = "",
    animated = true,
    replaceAnimations = false,
    updateIntervalMs = 0,
  }: {
    plan?: PlanView | null;
    promoPlans?: { base: PlanView; discounted: PlanView } | null;
    unitPricePlan?: PlanView | null;
    unitPriceSuffix?: string;
    method?: string;
    animated?: boolean;
    replaceAnimations?: boolean;
    updateIntervalMs?: number;
  } = $props();
</script>

{#if promoPlans}
  <span class="promo-price-pair">
    <s
      ><AnimatedPrice
        plan={promoPlans.base}
        {method}
        {animated}
        {replaceAnimations}
        {updateIntervalMs}
      /></s
    >
    <b
      ><AnimatedPrice
        plan={promoPlans.discounted}
        {method}
        {animated}
        {replaceAnimations}
        {updateIntervalMs}
      /></b
    >
  </span>
{:else}
  <span><AnimatedPrice {plan} {method} {animated} {replaceAnimations} {updateIntervalMs} /></span>
{/if}
{#if unitPricePlan}
  <small class="period-unit-price">
    <AnimatedPrice
      plan={unitPricePlan}
      {method}
      {animated}
      {replaceAnimations}
      {updateIntervalMs}
    />
    <span>{unitPriceSuffix}</span>
  </small>
{/if}

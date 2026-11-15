<script lang="ts">
  import type { BillingPlan } from "$lib/webapp/tariffs.js";
  import { isStarsPaymentMethod } from "$lib/webapp/tariffs.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import AnimatedNumber from "./AnimatedNumber.svelte";

  let {
    plan = null,
    method = "",
    animated = true,
    replaceAnimations = false,
    updateIntervalMs = 0,
  }: {
    plan?: BillingPlan | null;
    method?: string;
    animated?: boolean;
    replaceAnimations?: boolean;
    updateIntervalMs?: number;
  } = $props();

  const stars = $derived(isStarsPaymentMethod(method) && Number(plan?.stars_price || 0) > 0);
  const amount = $derived(stars ? Number(plan?.stars_price || 0) : Number(plan?.price || 0));
  const currency = $derived(String(plan?.currency || "RUB").toUpperCase());
  const suffix = $derived(stars ? " ⭐" : currency === "RUB" ? " ₽" : ` ${currency}`);
  // The cabinet's money format: whole amounts without ".00", others with two
  // digits after a dot ("221.10 ₽"). The whole part animates and the kopecks ride
  // in the suffix, so the element stays the same while a slider moves.
  const fixed = $derived(Number(amount || 0).toFixed(2));
  const cents = $derived(stars ? "00" : fixed.slice(-2));
  const fractional = $derived(cents !== "00");
</script>

<AnimatedNumber
  className="animated-price"
  value={fractional ? Number(fixed.slice(0, -3)) : amount}
  suffix={fractional ? `.${cents}${suffix}` : suffix}
  ariaLabel={fractional ? formatMoney(amount, currency) : `${amount}${suffix}`}
  format={{ maximumFractionDigits: 0 }}
  {animated}
  {replaceAnimations}
  {updateIntervalMs}
/>

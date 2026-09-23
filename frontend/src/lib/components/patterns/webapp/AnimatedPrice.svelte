<script lang="ts">
  import type { BillingPlan } from "$lib/webapp/tariffs.js";
  import { isStarsPaymentMethod } from "$lib/webapp/tariffs.js";
  import AnimatedNumber from "./AnimatedNumber.svelte";

  let {
    plan = null,
    method = "",
    replaceAnimations = false,
    updateIntervalMs = 0,
  }: {
    plan?: BillingPlan | null;
    method?: string;
    replaceAnimations?: boolean;
    updateIntervalMs?: number;
  } = $props();

  const stars = $derived(isStarsPaymentMethod(method) && Number(plan?.stars_price || 0) > 0);
  const amount = $derived(stars ? Number(plan?.stars_price || 0) : Number(plan?.price || 0));
  const currency = $derived(String(plan?.currency || "RUB").toUpperCase());
  const suffix = $derived(stars ? " ⭐" : currency === "RUB" ? " ₽" : ` ${currency}`);
</script>

<AnimatedNumber
  className="animated-price"
  value={amount}
  {suffix}
  ariaLabel={`${amount}${suffix}`}
  format={{ maximumFractionDigits: Number.isInteger(amount) ? 0 : 2 }}
  {replaceAnimations}
  {updateIntervalMs}
/>

<script lang="ts">
  import { formatCompactNumber } from "$lib/webapp/formatters.js";
  import type { PlanView, Translate } from "$lib/webapp/types.js";

  let {
    plan,
    t = (key) => key,
  }: {
    plan: PlanView;
    t?: Translate;
  } = $props();
</script>

<div class="trial-payment-summary">
  <span>
    <small>{t("wa_trial_duration_label", {}, "Duration")}</small>
    <strong>
      {t("wa_trial_days_left", { days: Number(plan.duration_days || 0) }, "{days} days")}
    </strong>
  </span>
  <span>
    <small>{t("wa_trial_traffic_label", {}, "Traffic")}</small>
    <strong>
      {Number(plan.traffic_gb || 0) > 0
        ? t("wa_pending_payment_traffic", {
            gb: formatCompactNumber(Number(plan.traffic_gb || 0)),
          })
        : t("wa_unlimited_traffic")}
    </strong>
  </span>
</div>

<style>
  .trial-payment-summary {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .trial-payment-summary > span {
    display: grid;
    gap: 4px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-inner);
    background: var(--surface-soft, color-mix(in srgb, var(--surface) 92%, var(--primary)));
  }

  .trial-payment-summary small {
    color: var(--muted);
  }
</style>

<script lang="ts">
  let {
    visible,
    days,
    period,
    bonusDays,
    endDate,
    t,
  }: {
    visible: boolean;
    days: number | null;
    period: string;
    bonusDays: number;
    endDate: string;
    t: (key: string, params?: Record<string, unknown>) => string;
  } = $props();
</script>

{#if visible && days}
  <p class="subscription-purchase-description" aria-live="polite">
    {t("wa_checkout_exact_period", { period, days })}
    {#if bonusDays > 0}{t("wa_checkout_bonus_days", { days: bonusDays })}{/if}
    {#if endDate}<br />{t("wa_checkout_end_date", {
        date: new Date(endDate).toLocaleDateString(),
      })}{/if}
  </p>
{/if}

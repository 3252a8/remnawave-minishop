<script lang="ts">
  import { CheckCircle2 } from "$components/ui/icons.js";
  import type { TrialDaysStrategy } from "$lib/webapp/trialDays.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    value = "add_remaining",
    onChange = () => {},
    t = (key) => key,
  }: {
    value?: TrialDaysStrategy;
    onChange?: (value: TrialDaysStrategy) => void;
    t?: Translate;
  } = $props();

  const options: Array<{
    value: TrialDaysStrategy;
    title: string;
    hint: string;
  }> = [
    {
      value: "add_remaining",
      title: "wa_trial_days_strategy_add",
      hint: "wa_trial_days_strategy_add_hint",
    },
    {
      value: "start_from_payment",
      title: "wa_trial_days_strategy_replace",
      hint: "wa_trial_days_strategy_replace_hint",
    },
  ];
</script>

<div class="payment-divider" aria-hidden="true"></div>
<p class="section-kicker">{t("wa_trial_days_strategy_title")}</p>
<div class="option-list" role="group" aria-label={t("wa_trial_days_strategy_title")}>
  {#each options as option (option.value)}
    <button
      class:active={value === option.value}
      class="option-row"
      type="button"
      aria-pressed={value === option.value}
      onclick={() => onChange(option.value)}
    >
      <span class="option-row-main">
        <strong>{t(option.title)}</strong>
        <small>{t(option.hint)}</small>
      </span>
      {#if value === option.value}
        <CheckCircle2 size={18} />
      {/if}
    </button>
  {/each}
</div>

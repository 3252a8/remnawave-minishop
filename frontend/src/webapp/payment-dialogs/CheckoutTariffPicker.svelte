<script lang="ts">
  import { ArrowRight, CheckCircle2 } from "$components/ui/icons.js";
  import type { TariffView, Translate } from "$lib/webapp/types.js";

  let {
    tariffs = [],
    selectedTariffKey = "",
    metaLabel = () => "",
    selectTariff = () => {},
    t = (key) => key,
  }: {
    tariffs?: TariffView[];
    selectedTariffKey?: string;
    metaLabel?: (tariff: TariffView) => string;
    selectTariff?: (tariff: TariffView) => void;
    t?: Translate;
  } = $props();
</script>

<div class="option-list tariff-list">
  {#each tariffs as tariff (tariff.key)}
    <button
      class:active={selectedTariffKey === tariff.key}
      class="option-row tariff-row"
      type="button"
      onclick={() => selectTariff(tariff)}
    >
      <span class="option-row-main">
        <strong>{tariff.title}</strong>
        <small>{tariff.description || t("wa_tariff_no_description")}</small>
      </span>
      <span class="option-row-meta">
        <em>{metaLabel(tariff)}</em>
        {#if selectedTariffKey === tariff.key}
          <CheckCircle2 size={18} />
        {:else}
          <ArrowRight size={17} />
        {/if}
      </span>
    </button>
  {/each}
</div>

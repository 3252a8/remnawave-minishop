<script lang="ts">
  import { ArrowRight, CheckCircle2 } from "$components/ui/icons.js";
  import TariffLimitFacts from "$components/patterns/webapp/TariffLimitFacts.svelte";
  import { tariffLimitFacts } from "$lib/webapp/tariffs.js";
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
      aria-pressed={selectedTariffKey === tariff.key}
      onclick={() => selectTariff(tariff)}
    >
      <div class="option-row-main">
        <div class="tariff-row-heading">
          <strong>{tariff.title}</strong>
          <TariffLimitFacts compact inline facts={tariffLimitFacts(tariff, { t })} {t} />
        </div>
        <div class="tariff-row-details">
          {#if tariff.description?.trim()}
            <small>{tariff.description}</small>
          {/if}
          <span class="option-row-meta">
            <em>{metaLabel(tariff)}</em>
            {#if selectedTariffKey === tariff.key}
              <CheckCircle2 size={18} />
            {:else}
              <ArrowRight size={17} />
            {/if}
          </span>
        </div>
      </div>
    </button>
  {/each}
</div>

<style>
  .tariff-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
    min-height: 0;
    gap: 8px;
    padding: 10px;
  }

  .tariff-row-heading {
    display: flex;
    flex-wrap: wrap;
    min-width: 0;
    align-items: center;
    justify-content: space-between;
    gap: 5px;
  }

  .option-row-main {
    gap: 6px;
  }

  .tariff-row-heading strong {
    min-width: 0;
    max-width: 100%;
    flex: 0 1 auto;
  }

  .tariff-row-details {
    display: flex;
    flex-wrap: wrap;
    min-width: 0;
    align-items: flex-end;
    gap: 4px 8px;
  }

  .tariff-row-details small {
    min-width: 0;
    flex: 1 1 12rem;
  }

  .option-row-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 0 1 auto;
    min-width: 0;
    max-width: 100%;
    margin-left: auto;
  }
</style>

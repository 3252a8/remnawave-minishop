<script lang="ts">
  import { Button } from "$components/ui/index.js";
  import Card from "$components/ui/card.svelte";
  import { Clock, RefreshCw } from "$components/ui/icons.js";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { BrandConfig, Translate } from "$lib/webapp/types.js";

  let { brand, brandTitle, t }: { brand: BrandConfig; brandTitle: string; t: Translate } = $props();
</script>

<section class="maintenance-screen" aria-labelledby="maintenance-title">
  <div class="maintenance-brand">
    <BrandMark {brand} size="md" />
    <span>{brandTitle}</span>
  </div>
  <Card class="maintenance-card">
    <div class="maintenance-copy" role="status" aria-live="polite">
      <span class="maintenance-icon" aria-hidden="true"><Clock size={28} /></span>
      <h1 id="maintenance-title">{t("wa_maintenance_title")}</h1>
      <p>{t("wa_maintenance_description")}</p>
    </div>
    <Button class="wide" onclick={() => window.location.reload()}>
      <RefreshCw size={17} />
      {t("wa_maintenance_retry")}
    </Button>
  </Card>
</section>

<style>
  .maintenance-screen {
    min-height: 100dvh;
    display: grid;
    grid-template-columns: minmax(0, 440px);
    place-content: safe center;
    justify-items: center;
    gap: 24px;
    padding: 32px 20px;
    box-sizing: border-box;
  }
  .maintenance-brand {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--text);
    font-size: 15px;
    font-weight: 700;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  :global(.card.maintenance-card) {
    display: grid;
    gap: 28px;
    width: min(100%, 440px);
    padding: clamp(24px, 5vw, 36px);
    box-sizing: border-box;
  }
  .maintenance-copy {
    display: grid;
    justify-items: center;
    gap: 16px;
    text-align: center;
  }
  .maintenance-icon {
    display: grid;
    place-items: center;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    color: var(--warning-text);
    background: var(--warning-soft);
    border: 1px solid var(--warning-border);
  }
  h1 {
    margin: 4px 0 0;
    color: var(--text);
    font-size: clamp(22px, 5vw, 26px);
    line-height: 1.25;
    overflow-wrap: anywhere;
  }
  p {
    margin: 0;
    width: 100%;
    text-align: left;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.65;
    overflow-wrap: anywhere;
  }
</style>

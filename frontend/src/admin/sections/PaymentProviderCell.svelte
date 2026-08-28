<script lang="ts">
  import { paymentProviderDisplay } from "$lib/admin/paymentTable.js";

  let { provider }: { provider: string | null | undefined } = $props();

  const providerDisplay = $derived(paymentProviderDisplay(provider));
  const providerLabel = $derived(providerDisplay.label);
  const logoUrl = $derived(providerDisplay.logoUrl);
  let logoFailed = $state(false);

  $effect(() => {
    logoUrl;
    logoFailed = false;
  });
</script>

<span class="admin-payment-provider" title={providerLabel}>
  <span class="admin-payment-provider-logo" aria-hidden="true">
    {#if logoUrl && !logoFailed}
      <img
        src={logoUrl}
        alt=""
        loading="lazy"
        decoding="async"
        onerror={() => (logoFailed = true)}
      />
    {:else}
      <span>{providerDisplay.fallbackEmoji}</span>
    {/if}
  </span>
  <span class="admin-payment-provider-name">{providerLabel}</span>
</span>

<style>
  .admin-payment-provider {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    max-width: 100%;
  }

  .admin-payment-provider-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    flex: 0 0 28px;
    overflow: hidden;
  }

  .admin-payment-provider-logo img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .admin-payment-provider-logo > span {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    border: 1px solid var(--admin-border);
    border-radius: 7px;
    background: color-mix(in srgb, var(--admin-bg) 78%, #ffffff);
    color: var(--admin-text);
    font-size: 17px;
    line-height: 1;
  }

  .admin-payment-provider-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>

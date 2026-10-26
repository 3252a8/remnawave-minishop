<script lang="ts">
  import { paymentProviderDisplay } from "$lib/admin/paymentTable.js";

  let {
    provider,
    at = (_key, _params, fallback) => fallback || "",
  }: {
    provider: string | null | undefined;
    at?: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  } = $props();

  const providerDisplay = $derived(paymentProviderDisplay(provider));
  const providerLabel = $derived(
    provider === "admin_gift"
      ? at("gifts_source_admin", {}, "From administrator")
      : provider === "subscription_days"
        ? at("payments_provider_subscription_days", {}, "Subscription days")
        : providerDisplay.label
  );
  const logoUrl = $derived(providerDisplay.logoUrl);
  let logoFailed = $state(false);

  $effect(() => {
    logoUrl;
    logoFailed = false;
  });
</script>

<span
  class="admin-payment-provider"
  class:admin-payment-provider-wrap={provider === "subscription_days"}
  title={providerLabel}
>
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
      {providerDisplay.fallbackEmoji}
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
    font-size: 28px;
    line-height: 1;
  }

  .admin-payment-provider-logo img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .admin-payment-provider-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-payment-provider-wrap {
    gap: 6px;
  }

  .admin-payment-provider-wrap .admin-payment-provider-logo {
    width: 18px;
    height: 18px;
    flex-basis: 18px;
    font-size: 18px;
  }

  .admin-payment-provider-wrap .admin-payment-provider-name {
    white-space: normal;
    overflow-wrap: anywhere;
    text-overflow: clip;
    line-height: 1.25;
  }
</style>

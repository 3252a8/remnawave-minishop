<script lang="ts">
  const PROVIDER_LOGO_FILES: Record<string, string> = {
    cloudpayments: "cloudpayments.png",
    cryptopay: "cryptopay.png",
    freekassa: "freekassa.png",
    heleket: "heleket.png",
    lava: "lava.png",
    overpay: "overpay.png",
    pally: "pally.png",
    paykilla: "paykilla.png",
    platega: "platega.png",
    severpay: "severpay.png",
    stars: "telegram-stars.png",
    stripe: "stripe.png",
    telegram_stars: "telegram-stars.png",
    tribute: "tribute.png",
    wata: "wata.png",
    yookassa: "yookassa.png",
  };

  let { provider }: { provider: string | null | undefined } = $props();

  const providerLabel = $derived(String(provider || "").trim() || "—");
  const providerKey = $derived(
    String(provider || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
  );
  const logoKey = $derived(
    providerKey.startsWith("platega")
      ? "platega"
      : providerKey.startsWith("wata")
        ? "wata"
        : providerKey
  );
  const logoUrl = $derived(
    PROVIDER_LOGO_FILES[logoKey] ? `/provider-logos/${PROVIDER_LOGO_FILES[logoKey]}` : ""
  );
  const fallback = $derived(
    providerLabel
      .split(/[^\p{L}\p{N}]+/u)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase()
      .slice(0, 2) || "P"
  );
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
      <span>{fallback}</span>
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
    font-size: 10px;
    font-weight: 800;
    line-height: 1;
  }

  .admin-payment-provider-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>

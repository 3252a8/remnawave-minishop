<script>
  import { onDestroy } from "svelte";

  import { cn } from "../utils.js";
  import { normalizeBrand } from "./browser.js";

  const LOGO_LOAD_TIMEOUT_MS = 10000;

  export let brand = {};
  export let logoUrl = "";
  export let size = "sm";
  export let animate = false;
  let className = "";
  export { className as class };

  const SIZE_CLASSES = {
    sm: "",
    md: "brand-mark-lg",
    lg: "brand-mark-xl",
    xl: "brand-mark-xl",
  };

  let loaded = false;
  let failed = false;
  let lastLogoUrl = "";
  let logoLoadTimer = null;
  let logoLoadTimerUrl = "";

  $: normalizedBrand = normalizeBrand({
    ...brand,
    logoUrl: logoUrl || brand?.logoUrl,
  });
  $: normalizedLogoUrl = normalizedBrand.logoUrl;
  $: sizeClass = SIZE_CLASSES[size] || "";

  $: if (normalizedLogoUrl !== lastLogoUrl) {
    lastLogoUrl = normalizedLogoUrl;
    loaded = false;
    failed = false;
  }
  $: if (normalizedLogoUrl && !loaded && !failed) armLogoLoadTimeout();
  $: if (!normalizedLogoUrl || loaded || failed) clearLogoLoadTimeout();

  onDestroy(() => {
    clearLogoLoadTimeout();
  });

  function clearLogoLoadTimeout() {
    if (logoLoadTimer) {
      window.clearTimeout(logoLoadTimer);
      logoLoadTimer = null;
    }
    logoLoadTimerUrl = "";
  }

  function armLogoLoadTimeout() {
    if (typeof window === "undefined") return;
    if (logoLoadTimer && logoLoadTimerUrl === normalizedLogoUrl) return;
    clearLogoLoadTimeout();
    logoLoadTimerUrl = normalizedLogoUrl;
    logoLoadTimer = window.setTimeout(() => {
      if (logoLoadTimerUrl === normalizedLogoUrl && !loaded) failed = true;
    }, LOGO_LOAD_TIMEOUT_MS);
  }
</script>

<div
  class={cn(
    "brand-mark",
    sizeClass,
    animate && "brand-mark-animate",
    normalizedLogoUrl && !failed && !loaded && "brand-mark-loading",
    normalizedLogoUrl && !failed && loaded && "brand-mark-loaded",
    className
  )}
  aria-busy={normalizedLogoUrl && !failed && !loaded ? "true" : undefined}
>
  {#if normalizedLogoUrl && !failed}
    {#if !loaded}
      <span class="brand-mark-spinner" aria-hidden="true"></span>
    {/if}
    <img
      class:loaded
      src={normalizedLogoUrl}
      alt=""
      loading="eager"
      decoding="async"
      fetchpriority="high"
      on:load={() => {
        loaded = true;
        clearLogoLoadTimeout();
      }}
      on:error={() => {
        failed = true;
        clearLogoLoadTimeout();
      }}
    />
  {/if}
</div>

<style>
  .brand-mark {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
    overflow: visible;
    font-size: 1.625rem;
  }

  .brand-mark img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .brand-mark img.loaded {
    opacity: 1;
  }

  .brand-mark.brand-mark-lg {
    width: 4.125rem;
    height: 4.125rem;
    font-size: 2.875rem;
  }

  .brand-mark.brand-mark-xl {
    width: 6rem;
    height: 6rem;
    font-size: 4.375rem;
  }

  .brand-mark.brand-mark-animate {
    animation: brand-mark-pulse 2s ease-in-out infinite;
  }

  .brand-mark-spinner {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .brand-mark-spinner::after {
    content: "";
    width: 1rem;
    height: 1rem;
    border: 2px solid currentColor;
    border-bottom-color: transparent;
    border-radius: 50%;
    animation: brand-mark-spin 0.8s linear infinite;
    opacity: 0.5;
  }

  @keyframes brand-mark-spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  @keyframes brand-mark-pulse {
    0%,
    100% {
      transform: scale(1);
    }
    50% {
      transform: scale(1.05);
    }
  }
</style>

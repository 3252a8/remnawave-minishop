<script lang="ts">
  let {
    themeKey,
    title,
    at,
    url,
  }: {
    themeKey: string;
    title: string;
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    url?: string;
  } = $props();
  let failed = $state(false);
  const imageUrl = $derived(
    url === undefined ? "/webapp-theme-assets/" + themeKey + "/preview.webp" : url
  );
  const source = $derived(
    typeof window !== "undefined" && window.location.pathname.startsWith("/demo/runtime/")
      ? imageUrl.replace("/webapp-theme-assets/", "/demo/runtime/themes/")
      : imageUrl
  );
  $effect(() => {
    void source;
    failed = false;
  });
</script>

<div class="theme-screenshot">
  {#if source && !failed}<img
      src={source}
      alt={at(
        "appearance_screenshot_alt",
        { theme: title },
        "{theme}: account home with demo data"
      )}
      loading="lazy"
      onerror={() => {
        failed = true;
      }}
    />
  {:else}<span
      >{at(
        "appearance_no_screenshot",
        {},
        "The author has not added a screenshot. Open the live preview."
      )}</span
    >{/if}
</div>

<style>
  .theme-screenshot {
    aspect-ratio: 16 / 10;
    overflow: hidden;
    display: grid;
    place-items: center;
    background: var(--admin-surface-2);
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
    display: block;
  }
  span {
    padding: 24px;
    color: var(--admin-muted);
    font-size: 12px;
    text-align: center;
  }
</style>

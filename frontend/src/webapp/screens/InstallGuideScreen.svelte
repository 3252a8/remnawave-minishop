<script>
  import { getContext, onMount } from "svelte";
  import { cubicOut } from "svelte/easing";
  import { fade, fly, scale } from "svelte/transition";
  import QRCode from "qrcode";
  import {
    ArrowLeft,
    Check,
    ChevronsUpDown,
    Copy,
    ExternalLink,
    Monitor,
    QrCode,
    Share2,
    Smartphone,
  } from "$components/ui/icons.js";
  import { AttentionDot, Spinner } from "$components/ui/index.js";
  import { Select } from "$components/ui/primitives.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";

  export let currentLang = "ru";
  export let telegramPlatform = "";
  export let user = {};
  export let subscription = {};
  export let goHome = () => {};
  export let openConnectLink = () => {};
  export let openExternalLink = () => {};
  export let openAppLink = null;
  export let copyText = async () => {};
  export let t = (key, _params = {}, fallback = "") => fallback || key;
  export let publicMode = false;

  const installGuidesStore = getContext("installGuidesStore");
  const colorTokens = {
    amber: "#f59e0b",
    blue: "#3b82f6",
    cyan: "#06b6d4",
    emerald: "#10b981",
    fuchsia: "#d946ef",
    gray: "#6b7280",
    green: "#22c55e",
    indigo: "#6366f1",
    lime: "#84cc16",
    neutral: "#737373",
    orange: "#f97316",
    pink: "#ec4899",
    purple: "#a855f7",
    red: "#ef4444",
    rose: "#f43f5e",
    sky: "#0ea5e9",
    slate: "#64748b",
    stone: "#78716c",
    teal: "#14b8a6",
    violet: "#8b5cf6",
    yellow: "#eab308",
    zinc: "#71717a",
  };
  let selectedPlatformKey = "";
  let selectedAppIndex = 0;
  let qrDataUrl = "";
  let lastQrValue = "";
  let qrRequestId = 0;

  onMount(() => {
    if (!publicMode) installGuidesStore?.load();
  });

  $: guideState = $installGuidesStore;
  $: config = guideState?.config || null;
  $: platforms = Object.entries(config?.platforms || {})
    .filter(([, platform]) => Array.isArray(platform?.apps) && platform.apps.length)
    .map(([key, platform]) => ({ key, ...platform }));
  $: platformOptions = platforms.map((platform) => ({
    value: platform.key,
    label: localized(platform.displayName, platform.key),
  }));
  $: detectedPlatformKey = detectPlatformKey(platforms.map((platform) => platform.key));
  $: if (platforms.length && !selectedPlatformKey) {
    selectedPlatformKey = detectedPlatformKey || platforms[0].key;
  }
  $: if (selectedPlatformKey && platforms.length && !platforms.some((p) => p.key === selectedPlatformKey)) {
    selectedPlatformKey = platforms[0].key;
  }
  $: selectedPlatform =
    platforms.find((platform) => platform.key === selectedPlatformKey) || platforms[0] || null;
  $: selectedPlatformLabel = selectedPlatform
    ? localized(selectedPlatform.displayName, selectedPlatform.key)
    : "";
  $: apps = selectedPlatform?.apps || [];
  $: if (selectedAppIndex >= apps.length) selectedAppIndex = 0;
  $: selectedApp = apps[selectedAppIndex] || apps[0] || null;
  $: guideSubscription = guideState?.subscription || subscription || {};
  $: finalSubscriptionLink =
    guideSubscription?.config_link || guideSubscription?.connect_url || subscription?.config_link || "";
  $: shareUrl = guideSubscription?.share_url || subscription?.install_share_url || "";
  $: if (finalSubscriptionLink !== lastQrValue) {
    lastQrValue = finalSubscriptionLink;
    updateQr(finalSubscriptionLink);
  }

  function localized(value, fallback = "") {
    if (typeof value === "string") return value;
    if (!value || typeof value !== "object") return fallback;
    const lang = String(currentLang || "ru").split("-")[0].toLowerCase();
    return (
      value[lang] ||
      value.ru ||
      value.en ||
      Object.values(value).find((item) => typeof item === "string" && item.trim()) ||
      fallback
    );
  }

  function iconSvg(key) {
    const iconKey = String(key || "").trim();
    return iconKey ? config?.svgLibrary?.[iconKey] || "" : "";
  }

  function iconColorStyle(color) {
    const raw = String(color || "").trim();
    const value = colorTokens[raw] || raw;
    return value ? `--install-icon-color:${value};` : "";
  }

  function selectPlatform(key) {
    selectedPlatformKey = key;
    selectedAppIndex = 0;
  }

  function platformFallbackIcon(key) {
    return key === "ios" || key === "android" || key === "androidTV" ? Smartphone : Monitor;
  }

  function detectPlatformKey(availableKeys) {
    const available = new Set(availableKeys || []);
    const tgPlatform = String(telegramPlatform || "").toLowerCase();
    const nav = typeof navigator === "undefined" ? {} : navigator;
    const userAgentDataPlatform = String(nav?.userAgentData?.platform || "").toLowerCase();
    const ua = String(nav?.userAgent || "").toLowerCase();
    const candidates = [];

    if (tgPlatform.includes("ios")) candidates.push("ios");
    if (tgPlatform.includes("android")) candidates.push("android");
    if (tgPlatform.includes("mac")) candidates.push("macos");
    if (tgPlatform.includes("windows")) candidates.push("windows");
    if (tgPlatform.includes("linux")) candidates.push("linux");

    if (userAgentDataPlatform.includes("android")) candidates.push("android");
    if (userAgentDataPlatform.includes("ios")) candidates.push("ios");
    if (userAgentDataPlatform.includes("mac")) candidates.push("macos");
    if (userAgentDataPlatform.includes("win")) candidates.push("windows");
    if (userAgentDataPlatform.includes("linux")) candidates.push("linux");

    if (ua.includes("apple tv")) candidates.push("appleTV");
    if (ua.includes("android") && /\btv\b|aft|bravia|shield/i.test(ua)) candidates.push("androidTV");
    if (/iphone|ipad|ipod/.test(ua)) candidates.push("ios");
    if (ua.includes("android")) candidates.push("android");
    if (ua.includes("windows")) candidates.push("windows");
    if (ua.includes("macintosh") || ua.includes("mac os")) candidates.push("macos");
    if (ua.includes("linux") || ua.includes("x11")) candidates.push("linux");

    return candidates.find((candidate) => available.has(candidate)) || "";
  }

  function templateValues() {
    const subscriptionLink = subscription?.config_link || subscription?.connect_url || "";
    const username = user?.username || user?.first_name || user?.id || "";
    return {
      HAPP_CRYPT3_LINK: subscriptionLink,
      HAPP_CRYPT4_LINK: subscriptionLink,
      SUBSCRIPTION_LINK: subscriptionLink,
      USERNAME: username,
    };
  }

  function resolveTemplate(value) {
    const replacements = templateValues();
    return String(value || "").replace(/\{\{\s*([A-Z0-9_]+)\s*\}\}/g, (_match, key) =>
      Object.prototype.hasOwnProperty.call(replacements, key) ? replacements[key] : ""
    );
  }

  function isUnsafeUrl(value) {
    const url = String(value || "").trim().toLowerCase();
    return !url || hasControlChars(url) || /^(javascript|data|vbscript):/.test(url);
  }

  function hasControlChars(value) {
    return Array.from(String(value || "")).some((char) => {
      const code = char.charCodeAt(0);
      return code <= 31 || code === 127;
    });
  }

  function openResolvedLink(url) {
    if (isUnsafeUrl(url)) {
      openConnectLink();
      return;
    }
    (openAppLink || openExternalLink)(url);
  }

  async function handleButton(button) {
    const value = resolveTemplate(button?.link);
    if (button?.type === "copyButton") {
      await copyText(
        value,
        localized(config?.baseTranslations?.linkCopiedToClipboard, t("wa_copied", {}, "Copied"))
      );
      return;
    }
    openResolvedLink(value);
  }

  async function updateQr(value) {
    const link = String(value || "").trim();
    const requestId = ++qrRequestId;
    if (!link) {
      qrDataUrl = "";
      return;
    }
    try {
      const url = await QRCode.toDataURL(link, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 640,
        color: {
          dark: "#000000",
          light: "#00000000",
        },
      });
      if (requestId === qrRequestId) qrDataUrl = url;
    } catch (_error) {
      if (requestId === qrRequestId) qrDataUrl = "";
    }
  }

  async function copySubscriptionLink() {
    await copyText(finalSubscriptionLink, t("wa_install_link_copied", {}, "Link copied"));
  }

  async function shareInstallGuide() {
    const url = shareUrl || (typeof window !== "undefined" ? window.location.href : "");
    if (!url) return;
    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share({
          title: localized(config?.baseTranslations?.installationGuideHeader, brandTitleFallback()),
          url,
        });
        return;
      } catch (_error) {
        void _error;
      }
    }
    await copyText(url, t("wa_install_share_copied", {}, "Share link copied"));
  }

  function brandTitleFallback() {
    return t("wa_install_title", {}, "Install");
  }
</script>

<main class="install-layout">
  <div class="install-topbar" class:public={publicMode}>
    {#if !publicMode}
      <Button
        class="install-back-btn"
        variant="secondary"
        size="icon"
        onclick={goHome}
        aria-label={t("wa_back", {}, "Back")}
      >
        <ArrowLeft size={21} />
      </Button>
    {/if}
    <div>
      <h1>{localized(config?.baseTranslations?.installationGuideHeader, t("wa_install_title", {}, "Install"))}</h1>
      <p>{t("wa_install_subtitle", {}, "Choose your platform and app.")}</p>
    </div>
    {#if guideState?.enabled && config && platforms.length}
      <div class="install-platform-topbar">
      <Select.Root
        type="single"
        value={selectedPlatformKey}
        items={platformOptions}
        onValueChange={selectPlatform}
      >
        <Select.Trigger
          class="install-platform-trigger"
          aria-label={t("wa_install_platform", {}, "Platform")}
        >
          <span class="install-platform-trigger-main">
            {#if selectedPlatform}
              {@const SelectedFallbackIcon = platformFallbackIcon(selectedPlatform.key)}
              {#if iconSvg(selectedPlatform.svgIconKey)}
                <span class="install-svg" aria-hidden="true">{@html iconSvg(selectedPlatform.svgIconKey)}</span>
              {:else}
                <svelte:component this={SelectedFallbackIcon} size={19} />
              {/if}
            {/if}
            <span>{selectedPlatformLabel}</span>
          </span>
          <ChevronsUpDown size={16} />
        </Select.Trigger>
        <Select.Content class="install-platform-content" side="bottom" align="start" sideOffset={6}>
          <Select.Viewport class="install-platform-viewport">
            {#each platforms as platform}
              {@const PlatformFallbackIcon = platformFallbackIcon(platform.key)}
              <Select.Item
                value={platform.key}
                label={localized(platform.displayName, platform.key)}
                class="install-platform-item"
              >
                <span class="install-platform-item-main">
                  {#if iconSvg(platform.svgIconKey)}
                    <span class="install-svg" aria-hidden="true">{@html iconSvg(platform.svgIconKey)}</span>
                  {:else}
                    <svelte:component this={PlatformFallbackIcon} size={18} />
                  {/if}
                  <span>{localized(platform.displayName, platform.key)}</span>
                </span>
                <Check size={15} class="install-platform-item-check" />
              </Select.Item>
            {/each}
          </Select.Viewport>
        </Select.Content>
      </Select.Root>
      </div>
    {/if}
  </div>

  {#if guideState?.loading && !guideState?.loaded}
    <div
      class="install-loading"
      role="status"
      aria-label={t("wa_install_loading", {}, "Loading instructions...")}
    >
      <Spinner size="lg" />
      <span>{t("wa_install_loading", {}, "Loading instructions...")}</span>
    </div>
  {:else if !guideState?.enabled || !config || !platforms.length}
    <Card class="install-empty">
      <p>{t("wa_install_unavailable", {}, "Instructions are unavailable.")}</p>
      <Button class="wide" onclick={openConnectLink}>
        <ExternalLink size={18} />
        {t("wa_install_and_configure")}
      </Button>
    </Card>
  {:else}

    {#key selectedPlatformKey}
      {#if apps.length > 1}
        <section
          class="install-selector-block"
          aria-label={t("wa_install_app", {}, "App")}
          in:fly={{ y: 8, duration: 180, easing: cubicOut }}
          out:fade={{ duration: 90 }}
        >
          <div class="install-section-title">
            <span>{t("wa_install_app", {}, "App")}</span>
          </div>
          <div
            class="install-apps"
            class:apps-mobile-remainder-one={apps.length % 2 === 1}
            class:apps-remainder-one={apps.length % 3 === 1}
            class:apps-remainder-two={apps.length % 3 === 2}
          >
            {#each apps as app, index (`${selectedPlatformKey}:${app.name}:${index}`)}
              <button
                class="install-app-button attention-wrap"
                class:active={selectedAppIndex === index}
                class:featured={app.featured}
                type="button"
                onclick={() => (selectedAppIndex = index)}
                in:scale={{
                  start: 0.97,
                  duration: 150 + Math.min(index, 5) * 18,
                  easing: cubicOut,
                }}
              >
                {#if app.featured}
                  <AttentionDot class="install-feature-star" />
                {/if}
                {#if iconSvg(app.svgIconKey)}
                  <span class="install-svg" aria-hidden="true">{@html iconSvg(app.svgIconKey)}</span>
                {/if}
                <span>{app.name}</span>
              </button>
            {/each}
          </div>
        </section>
      {/if}
    {/key}

    {#if selectedApp}
      {#key `${selectedPlatformKey}:${selectedAppIndex}:${selectedApp.name}`}
        <section
          class="install-steps"
          aria-label={selectedApp.name}
          in:fly={{ y: 12, duration: 190, easing: cubicOut }}
          out:fade={{ duration: 90 }}
        >
          {#each selectedApp.blocks as block, blockIndex (`${selectedPlatformKey}:${selectedApp.name}:${blockIndex}:${localized(block.title)}`)}
            <div
              class="install-step-motion"
              in:fly={{
                y: 10,
                duration: 170 + Math.min(blockIndex, 6) * 18,
                easing: cubicOut,
              }}
            >
              <Card class="install-step">
                <div class="install-step-icon" style={iconColorStyle(block.svgIconColor)} aria-hidden="true">
                  {#if iconSvg(block.svgIconKey)}
                    {@html iconSvg(block.svgIconKey)}
                  {:else}
                    <Check size={19} />
                  {/if}
                </div>
                <div class="install-step-body">
                  <h2>{localized(block.title)}</h2>
                  <p>{localized(block.description)}</p>
                  {#if block.buttons?.length}
                    <div class="install-actions">
                      {#each block.buttons as button}
                        <Button
                          variant={button.type === "copyButton" ? "secondary" : "default"}
                          onclick={() => handleButton(button)}
                        >
                          {#if button.type === "copyButton"}
                            <Copy size={16} />
                          {:else}
                            <ExternalLink size={16} />
                          {/if}
                          {localized(button.text)}
                        </Button>
                      {/each}
                    </div>
                  {/if}
                </div>
              </Card>
            </div>
          {/each}
        </section>
      {/key}
      {#if finalSubscriptionLink && !publicMode}
        <div
          class="install-qr-divider"
          aria-hidden="true"
          in:fade={{ duration: 180 }}
        >
          <svg viewBox="0 0 240 18" preserveAspectRatio="none">
            <path
              d="M0 9 Q 4 2 8 9 T 16 9 T 24 9 T 32 9 T 40 9 T 48 9 T 56 9 T 64 9 T 72 9 T 80 9 T 88 9 T 96 9 T 104 9 T 112 9 T 120 9 T 128 9 T 136 9 T 144 9 T 152 9 T 160 9 T 168 9 T 176 9 T 184 9 T 192 9 T 200 9 T 208 9 T 216 9 T 224 9 T 232 9 T 240 9"
            />
          </svg>
        </div>
        <div
          class="install-subscription-motion"
          in:fly={{ y: 10, duration: 200, easing: cubicOut }}
        >
          <Card class="install-subscription-card">
            <div class="install-subscription-header">
              <div class="install-subscription-header-icon" aria-hidden="true">
                <QrCode size={20} />
              </div>
              <div class="install-subscription-heading">
                <h2>{t("wa_install_subscription_link", {}, "Subscription link")}</h2>
                <p>{t("wa_install_subscription_link_hint", {}, "Scan the QR code or copy the link.")}</p>
              </div>
            </div>
            <div class="install-subscription-body">
              {#if qrDataUrl}
                <div class="install-qr-wrap" in:scale={{ start: 0.96, duration: 180, easing: cubicOut }}>
                  <img src={qrDataUrl} alt={t("wa_install_qr_alt", {}, "Subscription QR code")} />
                </div>
              {/if}
              <div class="install-actions install-subscription-actions">
                <Button variant="secondary" onclick={copySubscriptionLink}>
                  <Copy size={16} />
                  {t("wa_install_copy_subscription_link", {}, "Copy link")}
                </Button>
                <Button onclick={shareInstallGuide}>
                  <Share2 size={16} />
                  {t("wa_install_share", {}, "Share")}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      {/if}
    {/if}
  {/if}
</main>

<style>
  .install-layout {
    display: grid;
    gap: 16px;
    padding: 18px 16px 96px;
  }

  .install-topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }

  .install-topbar.public {
    grid-template-columns: minmax(0, 1fr);
  }

  :global(.install-back-btn) {
    width: 44px;
    min-width: 44px;
    height: 44px;
    min-height: 44px;
    padding: 0;
    border-color: var(--border-strong);
    color: var(--text);
  }

  :global(.install-back-btn svg) {
    width: 21px;
    height: 21px;
    stroke-width: 2.6;
  }

  .install-topbar h1 {
    margin: 0;
    color: var(--text);
    font-size: 22px;
    line-height: 1.15;
  }

  .install-platform-topbar {
    grid-column: 1 / -1;
    min-width: 0;
  }

  .install-topbar p,
  :global(.install-empty) p,
  .install-step-body p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
  }

  :global(.install-empty) {
    display: grid;
    gap: 14px;
  }

  .install-loading {
    display: grid;
    min-height: min(360px, 48dvh);
    place-items: center;
    align-content: center;
    gap: 12px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
    animation: install-loader-enter 0.16s ease-out both;
  }

  .install-loading :global(.ui-spinner) {
    color: var(--accent);
  }

  .install-selector-block {
    display: grid;
    gap: 9px;
  }

  .install-section-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .install-apps {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .install-apps.apps-mobile-remainder-one button:last-child {
    grid-column: 1 / -1;
  }

  .install-apps button {
    display: flex;
    min-height: 48px;
    align-items: center;
    gap: 9px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--panel) 88%, transparent);
    color: var(--text);
    padding: 10px;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transform: translateY(0);
    transition:
      border-color 0.18s ease,
      background 0.18s ease,
      box-shadow 0.18s ease,
      color 0.18s ease,
      transform 0.18s ease;
  }

  .install-apps button.active {
    border-color: color-mix(in srgb, var(--accent) 70%, var(--border));
    background: color-mix(in srgb, var(--accent) 12%, var(--panel));
    box-shadow: 0 10px 24px color-mix(in srgb, var(--accent) 12%, transparent);
    transform: translateY(-1px);
  }

  .install-apps button:focus-visible {
    outline: 0;
    border-color: color-mix(in srgb, var(--accent) 72%, var(--border));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
  }

  .install-apps button:active {
    transform: translateY(0) scale(0.99);
  }

  :global(.install-platform-trigger) {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 48px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--panel) 88%, transparent);
    color: var(--text);
    padding: 0 12px;
    font: inherit;
    text-align: left;
    box-shadow: var(--shadow-soft);
  }

  :global(.install-platform-trigger:focus-visible),
  :global(.install-platform-trigger[data-state="open"]) {
    outline: 0;
    border-color: color-mix(in srgb, var(--accent) 68%, var(--border));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
  }

  :global(.install-platform-trigger > svg) {
    color: var(--muted);
  }

  .install-platform-trigger-main,
  .install-platform-item-main {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .install-platform-trigger-main > span:last-child,
  .install-platform-item-main > span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.install-platform-content) {
    z-index: 140;
    width: min(300px, calc(100vw - 32px));
    min-width: min(300px, calc(100vw - 32px));
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    background: var(--panel-3);
    box-shadow: var(--shadow-popover);
    overflow: hidden;
    box-sizing: border-box;
    animation: dropdown-enter 0.16s ease-out both;
  }

  :global(.install-platform-viewport) {
    max-height: min(290px, 48dvh);
    padding: 6px;
  }

  :global(.install-platform-item) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 40px;
    border-radius: 6px;
    padding: 8px 9px;
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
  }

  :global(.install-platform-item[data-highlighted]) {
    background: var(--surface-hover);
  }

  :global(.install-platform-item-check) {
    flex: 0 0 auto;
    color: var(--accent);
    opacity: 0;
  }

  :global(.install-platform-item[data-selected] .install-platform-item-check) {
    opacity: 1;
  }

  .install-apps button {
    position: relative;
    align-items: flex-start;
    flex-direction: column;
    gap: 5px;
    overflow: visible;
  }

  .install-apps button > span {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  :global(.install-feature-star.attention-dot) {
    top: 8px;
    right: 8px;
    width: 16px;
    min-width: 16px;
    height: 16px;
    border-radius: 0;
    background: #facc15;
    clip-path: polygon(
      50% 0%,
      61% 35%,
      98% 35%,
      68% 56%,
      79% 91%,
      50% 70%,
      21% 91%,
      32% 56%,
      2% 35%,
      39% 35%
    );
    transform: none;
    animation: install-star-pulse 1.6s ease-out infinite;
  }

  .install-svg,
  .install-step-icon {
    display: inline-flex;
    flex: 0 0 auto;
    color: var(--install-icon-color, var(--accent));
  }

  .install-svg :global(svg),
  .install-step-icon :global(svg) {
    width: 19px;
    height: 19px;
    color: currentColor;
  }

  .install-steps {
    display: grid;
    gap: 10px;
  }

  .install-step-motion {
    min-width: 0;
  }

  :global(.install-step) {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 12px;
    transition:
      border-color 0.18s ease,
      background 0.18s ease,
      transform 0.18s ease,
      box-shadow 0.18s ease;
  }

  :global(.install-step:hover) {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--accent) 24%, var(--border));
  }

  .install-qr-divider {
    display: grid;
    place-items: center;
    height: 24px;
    color: var(--border-strong);
    opacity: 0.72;
  }

  .install-qr-divider svg {
    display: block;
    width: 100%;
    height: 18px;
    overflow: visible;
  }

  .install-qr-divider path {
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
  }

  :global(.install-subscription-card) {
    display: grid;
    gap: 12px;
    justify-self: stretch;
    transition:
      border-color 0.18s ease,
      transform 0.18s ease,
      box-shadow 0.18s ease;
  }

  .install-subscription-motion {
    display: grid;
    min-width: 0;
  }

  :global(.install-subscription-card:hover) {
    transform: translateY(-1px);
    border-color: color-mix(in srgb, var(--accent) 24%, var(--border));
  }

  .install-subscription-header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
    gap: 12px;
    padding: 2px 0 12px;
    border-bottom: 1px solid var(--border);
  }

  .install-subscription-header-icon {
    display: inline-flex;
    width: 38px;
    height: 38px;
    align-items: center;
    justify-content: center;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
    border-radius: 8px;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .install-subscription-header-icon :global(svg) {
    width: 20px;
    height: 20px;
  }

  .install-subscription-heading {
    min-width: 0;
  }

  .install-subscription-heading h2 {
    margin: 0 0 4px;
    color: var(--text);
    font-size: 16px;
    line-height: 1.25;
  }

  .install-subscription-heading p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.45;
  }

  .install-subscription-body {
    display: grid;
    gap: 10px;
  }

  .install-qr-wrap {
    display: grid;
    width: 60%;
    aspect-ratio: 1;
    place-items: center;
    justify-self: center;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: transparent;
    box-sizing: border-box;
  }

  .install-qr-wrap img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  :global(.theme-dark) .install-qr-wrap img {
    filter: brightness(0) invert(1);
  }

  .install-step-icon {
    width: 36px;
    height: 36px;
    align-items: center;
    justify-content: center;
    border: 1px solid color-mix(in srgb, currentColor 38%, var(--border));
    border-radius: 8px;
    background: color-mix(in srgb, currentColor 12%, transparent);
  }

  .install-step-body {
    display: grid;
    align-content: center;
    gap: 7px;
    min-width: 0;
  }

  .install-step-body h2 {
    margin: 0;
    color: var(--text);
    font-size: 16px;
    line-height: 1.25;
  }

  .install-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding-top: 3px;
  }

  .install-actions :global(.btn) {
    flex: 1 1 150px;
  }

  .install-subscription-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    align-content: start;
    padding-top: 0;
  }

  .install-subscription-actions :global(.btn) {
    width: 100%;
    flex: 0 0 auto;
  }

  @media (min-width: 520px) {
    .install-apps {
      grid-template-columns: repeat(6, minmax(0, 1fr));
    }

    .install-apps button,
    .install-apps.apps-mobile-remainder-one button:last-child {
      grid-column: span 2;
    }

    .install-apps.apps-remainder-one button:last-child {
      grid-column: 1 / -1;
    }

    .install-apps.apps-remainder-two button:nth-last-child(-n + 2) {
      grid-column: span 3;
    }
  }

  @media (hover: hover) {
    .install-apps button:hover {
      border-color: color-mix(in srgb, var(--accent) 34%, var(--border));
      background: color-mix(in srgb, var(--text) 4%, var(--panel));
      transform: translateY(-1px);
    }

    .install-apps button.active:hover {
      background: color-mix(in srgb, var(--accent) 15%, var(--panel));
      transform: translateY(-2px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .install-apps button,
    :global(.install-step),
    :global(.install-subscription-card) {
      transition: none;
      transform: none;
    }

    .install-apps button.active,
    .install-apps button:active,
    .install-apps button:hover,
    .install-apps button.active:hover,
    :global(.install-step:hover),
    :global(.install-subscription-card:hover) {
      transform: none;
    }
  }

  @media (min-width: 1024px) {
    .install-topbar {
      grid-template-columns: auto minmax(0, 1fr) minmax(260px, 340px);
    }

    .install-topbar.public {
      grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
    }

    .install-platform-topbar {
      grid-column: auto;
    }

    .install-platform-topbar :global(.install-platform-trigger) {
      min-height: 44px;
    }

    :global(.install-subscription-card) {
      width: fit-content;
      max-width: 100%;
      justify-self: center;
      padding: 16px;
    }

    .install-subscription-header,
    .install-subscription-body {
      width: clamp(300px, 28vw, 340px);
      max-width: 100%;
    }

    .install-qr-wrap {
      justify-self: center;
    }
  }

  @keyframes install-star-pulse {
    0% {
      filter: drop-shadow(0 0 0 rgba(250, 204, 21, 0.72));
      transform: scale(1);
    }

    65% {
      filter: drop-shadow(0 0 9px rgba(250, 204, 21, 0));
      transform: scale(1.18);
    }

    100% {
      filter: drop-shadow(0 0 0 rgba(250, 204, 21, 0));
      transform: scale(1);
    }
  }

  @keyframes install-loader-enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }

    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>

<script lang="ts">
  import { getInstallGuidesStore } from "$lib/webapp/context";
  import { onDestroy, onMount } from "svelte";
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
  import "./InstallGuideScreen.css";
  import { createHeightStageAnimator } from "$lib/webapp/motion/heightStage.js";
  import {
    detectInstallPlatformKey,
    installIconColorStyle,
    isUnsafeInstallUrl,
    localizedInstallValue,
    renderInstallQrDataUrl,
    resolveInstallButtonAction,
  } from "$lib/webapp/installGuideRuntime.js";

  type AnyRecord = Record<string, any>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type HeightStageAnimator = {
    animate(update: () => void): void;
    destroy(): void;
  };
  type HeightStageState = {
    instant: boolean;
    locked: boolean;
    style: string;
  };

  const createInstallStageAnimator = createHeightStageAnimator as unknown as (options: {
    durationMs: number;
    getElement: () => HTMLElement | null;
    settleDelayMs: number;
    setState: (state: HeightStageState) => void;
  }) => HeightStageAnimator;

  let {
    currentLang = "ru",
    telegramPlatform = "",
    user = {},
    subscription = {},
    goHome = () => {},
    openConnectLink = () => {},
    openExternalLink = () => {},
    openAppLink = null,
    copyText = async () => {},
    t = (key, _params = {}, fallback = "") => fallback || key,
    publicMode = false,
  }: {
    currentLang?: string;
    telegramPlatform?: string;
    user?: AnyRecord;
    subscription?: AnyRecord;
    goHome?: () => void;
    openConnectLink?: (url?: string) => void;
    openExternalLink?: (url: string) => void;
    openAppLink?: ((url: string) => void) | null;
    copyText?: (text: string, message?: string) => Promise<void>;
    t?: Translate;
    publicMode?: boolean;
  } = $props();

  const installGuidesStore = getInstallGuidesStore();
  const STAGE_HEIGHT_ANIMATION_MS = 360;
  const CARD_STAGGER_MS = 46;
  const QR_DELAY_EXTRA_MS = 90;
  let selectedPlatformKey = $state("");
  let selectedAppIndex = $state(0);
  let qrDataUrl = $state("");
  let lastQrValue = $state("");
  let qrRequestId = 0;
  let installContentStage = $state<HTMLElement | null>(null);
  let stageHeightStyle = $state("");
  let stageHeightLocked = $state(false);
  let stageHeightInstant = $state(false);
  const selectContentProps = { trapFocus: false } as Record<string, unknown>;
  const installStageAnimator = createInstallStageAnimator({
    durationMs: STAGE_HEIGHT_ANIMATION_MS,
    getElement: () => installContentStage,
    settleDelayMs: QR_DELAY_EXTRA_MS + 80,
    setState: setInstallStageState,
  });

  onMount(() => {
    if (!publicMode) installGuidesStore?.load();
  });

  onDestroy(() => installStageAnimator.destroy());

  const config = $derived((installGuidesStore?.config || null) as AnyRecord | null);
  const platforms = $derived(
    Object.entries((config?.platforms || {}) as Record<string, AnyRecord>)
      .filter(([, platform]) => Array.isArray(platform?.apps) && platform.apps.length)
      .map(([key, platform]) => ({ key, ...platform }) as AnyRecord & { key: string })
  );
  const platformOptions = $derived(
    platforms.map((platform) => ({
      value: platform.key,
      label: localized(platform.displayName, platform.key),
    }))
  );
  const detectedPlatformKey = $derived(
    detectInstallPlatformKey(
      platforms.map((platform) => platform.key),
      telegramPlatform
    )
  );
  $effect(() => {
    if (!platforms.length || selectedPlatformKey) return;
    selectedPlatformKey = detectedPlatformKey || platforms[0].key;
  });
  $effect(() => {
    if (!selectedPlatformKey || !platforms.length) return;
    if (platforms.some((p) => p.key === selectedPlatformKey)) return;
    selectedPlatformKey = platforms[0].key;
  });
  const selectedPlatform = $derived(
    platforms.find((platform) => platform.key === selectedPlatformKey) || platforms[0] || null
  );
  const selectedPlatformLabel = $derived(
    selectedPlatform ? localized(selectedPlatform.displayName, selectedPlatform.key) : ""
  );
  const apps = $derived(selectedPlatform?.apps || []);
  $effect(() => {
    if (selectedAppIndex >= apps.length) selectedAppIndex = 0;
  });
  const selectedApp = $derived(apps[selectedAppIndex] || apps[0] || null);
  const selectedBlocks = $derived(Array.isArray(selectedApp?.blocks) ? selectedApp.blocks : []);
  const hasAppCard = $derived(apps.length > 0);
  const stepsDelayOffset = $derived(hasAppCard ? apps.length + 1 : 0);
  const qrDelayIndex = $derived(stepsDelayOffset + selectedBlocks.length + 1);
  const installStageStyle = $derived(
    `${stageHeightStyle} --motion-stage-duration:${STAGE_HEIGHT_ANIMATION_MS}ms;`
  );
  const guideSubscription = $derived(installGuidesStore?.subscription || subscription || {});
  const finalSubscriptionLink = $derived(
    guideSubscription?.config_link ||
      guideSubscription?.connect_url ||
      subscription?.config_link ||
      ""
  );
  const shareUrl = $derived(guideSubscription?.share_url || subscription?.install_share_url || "");
  $effect(() => {
    if (finalSubscriptionLink === lastQrValue) return;
    lastQrValue = finalSubscriptionLink;
    updateQr(finalSubscriptionLink);
  });

  function localized(value: unknown, fallback = ""): string {
    return localizedInstallValue(value, currentLang, fallback);
  }

  function iconSvg(key: unknown): string {
    const iconKey = String(key || "").trim();
    return iconKey ? config?.svgLibrary?.[iconKey] || "" : "";
  }

  function iconColorStyle(color: unknown): string {
    return installIconColorStyle(color);
  }

  function setInstallStageState({ instant, locked, style }: HeightStageState) {
    stageHeightInstant = instant;
    stageHeightLocked = locked;
    stageHeightStyle = style;
  }

  function selectPlatform(key: string) {
    if (key === selectedPlatformKey) return;
    installStageAnimator.animate(() => {
      selectedPlatformKey = key;
      selectedAppIndex = 0;
    });
  }

  function selectApp(index: number) {
    if (index === selectedAppIndex) return;
    installStageAnimator.animate(() => {
      selectedAppIndex = index;
    });
  }

  function installMotionStyle(index: number, extraDelay = 0) {
    const delay = Math.max(0, index) * CARD_STAGGER_MS + Math.max(0, extraDelay);
    return `--motion-delay:${delay}ms;`;
  }

  function platformFallbackIcon(key: string) {
    return key === "ios" || key === "android" || key === "androidTV" ? Smartphone : Monitor;
  }

  function openResolvedLink(url: string) {
    if (isUnsafeInstallUrl(url)) {
      openConnectLink();
      return;
    }
    (openAppLink || openExternalLink)(url);
  }

  async function handleButton(button: AnyRecord) {
    const action = resolveInstallButtonAction(button, { subscription, user });
    if (action.kind === "copy") {
      await copyText(
        action.value,
        localized(config?.baseTranslations?.linkCopiedToClipboard, t("wa_copied", {}, "Copied"))
      );
      return;
    }
    openResolvedLink(action.value);
  }

  async function updateQr(value: unknown) {
    const requestId = ++qrRequestId;
    const url = await renderInstallQrDataUrl(value, (link) =>
      QRCode.toDataURL(link, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 640,
        color: {
          dark: "#000000",
          light: "#00000000",
        },
      })
    );
    if (requestId === qrRequestId) qrDataUrl = url;
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
      <h1>
        {localized(
          config?.baseTranslations?.installationGuideHeader,
          t("wa_install_title", {}, "Install")
        )}
      </h1>
      <p>{t("wa_install_subtitle", {}, "Choose your platform and app.")}</p>
    </div>
    {#if installGuidesStore?.enabled && config && platforms.length}
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
                  <span class="install-svg" aria-hidden="true"
                    >{@html iconSvg(selectedPlatform.svgIconKey)}</span
                  >
                {:else}
                  <SelectedFallbackIcon size={19} />
                {/if}
              {/if}
              <span>{selectedPlatformLabel}</span>
            </span>
            <ChevronsUpDown size={16} />
          </Select.Trigger>
          <Select.Content
            class="install-platform-content"
            side="bottom"
            align="start"
            sideOffset={6}
            {...selectContentProps}
          >
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
                      <span class="install-svg" aria-hidden="true"
                        >{@html iconSvg(platform.svgIconKey)}</span
                      >
                    {:else}
                      <PlatformFallbackIcon size={18} />
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

  {#if installGuidesStore?.loading && !installGuidesStore?.loaded}
    <div
      class="install-loading motion-fade-up"
      role="status"
      aria-label={t("wa_install_loading", {}, "Loading instructions...")}
    >
      <Spinner size="lg" />
      <span>{t("wa_install_loading", {}, "Loading instructions...")}</span>
    </div>
  {:else if !installGuidesStore?.enabled || !config || !platforms.length}
    <Card class="install-empty">
      <p>{t("wa_install_unavailable", {}, "Instructions are unavailable.")}</p>
      <Button class="wide" onclick={openConnectLink}>
        <ExternalLink size={18} />
        {t("wa_install_and_configure")}
      </Button>
    </Card>
  {:else}
    <div
      class="install-content-stage motion-height-stage"
      class:motion-height-locked={stageHeightLocked}
      class:motion-height-instant={stageHeightInstant}
      style={installStageStyle}
      bind:this={installContentStage}
    >
      {#key selectedPlatformKey}
        {#if hasAppCard}
          <section
            class="install-selector-block motion-enter-card"
            style={installMotionStyle(0)}
            aria-label={t("wa_install_app", {}, "App")}
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
                  class="install-app-button attention-wrap motion-enter-card"
                  class:active={selectedAppIndex === index}
                  class:featured={app.featured}
                  style={installMotionStyle(index + 1)}
                  type="button"
                  onclick={() => selectApp(index)}
                >
                  {#if app.featured}
                    <AttentionDot class="install-feature-star" />
                  {/if}
                  {#if iconSvg(app.svgIconKey)}
                    <span class="install-svg" aria-hidden="true"
                      >{@html iconSvg(app.svgIconKey)}</span
                    >
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
            style={installMotionStyle(stepsDelayOffset)}
          >
            {#each selectedBlocks as block, blockIndex (`${selectedPlatformKey}:${selectedApp.name}:${blockIndex}:${localized(block.title)}`)}
              <div
                class="install-step-motion motion-enter-card"
                style={installMotionStyle(stepsDelayOffset + blockIndex)}
              >
                <Card class="install-step">
                  <div
                    class="install-step-icon"
                    style={iconColorStyle(block.svgIconColor)}
                    aria-hidden="true"
                  >
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
            class="install-qr-divider motion-enter-card"
            style={installMotionStyle(qrDelayIndex, QR_DELAY_EXTRA_MS)}
            aria-hidden="true"
          >
            <svg viewBox="0 0 240 18" preserveAspectRatio="none">
              <path
                d="M0 9 Q 4 2 8 9 T 16 9 T 24 9 T 32 9 T 40 9 T 48 9 T 56 9 T 64 9 T 72 9 T 80 9 T 88 9 T 96 9 T 104 9 T 112 9 T 120 9 T 128 9 T 136 9 T 144 9 T 152 9 T 160 9 T 168 9 T 176 9 T 184 9 T 192 9 T 200 9 T 208 9 T 216 9 T 224 9 T 232 9 T 240 9"
              />
            </svg>
          </div>
          <div
            class="install-subscription-motion motion-enter-card"
            style={installMotionStyle(qrDelayIndex + 1, QR_DELAY_EXTRA_MS)}
          >
            <Card class="install-subscription-card">
              <div class="install-subscription-header">
                <div class="install-subscription-header-icon" aria-hidden="true">
                  <QrCode size={20} />
                </div>
                <div class="install-subscription-heading">
                  <h2>{t("wa_install_subscription_link", {}, "Subscription link")}</h2>
                  <p>
                    {t(
                      "wa_install_subscription_link_hint",
                      {},
                      "Scan the QR code or copy the link."
                    )}
                  </p>
                </div>
              </div>
              <div class="install-subscription-body">
                <div class="install-qr-wrap" class:ready={qrDataUrl}>
                  {#if qrDataUrl}
                    <img
                      class="motion-scale-in"
                      src={qrDataUrl}
                      alt={t("wa_install_qr_alt", {}, "Subscription QR code")}
                    />
                  {:else}
                    <span class="install-qr-placeholder motion-shimmer" aria-hidden="true"></span>
                  {/if}
                </div>
                <div class="install-actions install-subscription-actions">
                  <Button onclick={() => openResolvedLink(finalSubscriptionLink)}>
                    <ExternalLink size={16} />
                    {t("wa_install_open_subscription_link", {}, "Open in app")}
                  </Button>
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
    </div>
  {/if}
</main>

<script lang="ts">
  import {
    Gift,
    Handshake,
    Home,
    LifeBuoy,
    Settings as SettingsIcon,
    Shield,
    ShieldCheck,
    Smartphone,
  } from "$components/ui/icons.js";
  import { AttentionDot } from "$components/ui/index.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Action = () => void;

  type Props = {
    activeTab?: string;
    brand?: Record<string, unknown>;
    brandTitle?: string;
    bonusesNavigationVisible?: boolean;
    devicesEnabled?: boolean;
    hasUnlinkedIdentity?: boolean;
    isAdmin?: boolean;
    onAdmin?: Action;
    onDevices?: Action;
    onHome?: Action;
    onInvite?: Action;
    onPartner?: Action;
    partnerNavigationVisible?: boolean;
    partnerSettingsVisible?: boolean;
    onSettings?: Action;
    onSecurity?: Action;
    screen?: string;
    onSupport?: Action;
    supportEnabled?: boolean;
    supportUnreadCount?: number;
    supportUnreadLoaded?: boolean;
    supportUnreadLoading?: boolean;
    t?: Translate;
  };

  let {
    activeTab = "home",
    brand = {},
    brandTitle = "",
    bonusesNavigationVisible = true,
    devicesEnabled = false,
    supportEnabled = true,
    supportUnreadCount = 0,
    supportUnreadLoading = false,
    supportUnreadLoaded = false,
    hasUnlinkedIdentity = false,
    isAdmin = false,
    onAdmin = () => {},
    onDevices = () => {},
    onHome = () => {},
    onInvite = () => {},
    onPartner = () => {},
    partnerNavigationVisible = false,
    partnerSettingsVisible = false,
    screen = "home",
    onSupport = () => {},
    onSettings = () => {},
    onSecurity = () => {},
    t = (key) => key,
  }: Props = $props();

  const visibleNavItems = $derived(
    2 +
      (bonusesNavigationVisible ? 1 : 0) +
      (partnerNavigationVisible ? 1 : 0) +
      (devicesEnabled ? 1 : 0) +
      (supportEnabled ? 1 : 0)
  );
  const adminLabel = $derived(t("wa_nav_admin", {}, "Admin panel"));
</script>

<nav
  class:bottom-nav-devices={devicesEnabled}
  class:bottom-nav-many={visibleNavItems >= 5}
  class="bottom-nav"
  style={`--bottom-nav-visible-items: ${visibleNavItems}`}
  aria-label={t("wa_navigation")}
>
  <div class="rail-brand" aria-hidden="true">
    <BrandMark {brand} />
    <strong>{brandTitle}</strong>
  </div>
  <button
    data-nav-level="primary"
    class:active={activeTab === "home"}
    type="button"
    aria-label={t("wa_nav_home")}
    title={t("wa_nav_home")}
    onclick={onHome}
  >
    <Home size={21} />
    <span class="bottom-nav-label">{t("wa_nav_home")}</span>
  </button>
  {#if bonusesNavigationVisible}
    <button
      data-nav-level="primary"
      class:active={activeTab === "invite"}
      type="button"
      aria-label={t("wa_nav_bonuses")}
      title={t("wa_nav_bonuses")}
      onclick={onInvite}
    >
      <Gift size={21} />
      <span class="bottom-nav-label">{t("wa_nav_bonuses")}</span>
    </button>
  {/if}
  {#if partnerNavigationVisible}
    <button
      data-nav-level="primary"
      class:active={activeTab === "partner"}
      type="button"
      aria-label={t("wa_nav_partner")}
      title={t("wa_nav_partner")}
      onclick={onPartner}
    >
      <Handshake size={21} />
      <span class="bottom-nav-label">{t("wa_nav_partner")}</span>
    </button>
  {/if}
  {#if devicesEnabled}
    <button
      data-nav-level="primary"
      class:active={activeTab === "devices"}
      type="button"
      aria-label={t("wa_nav_devices")}
      title={t("wa_nav_devices")}
      onclick={onDevices}
    >
      <Smartphone size={21} />
      <span class="bottom-nav-label">{t("wa_nav_devices")}</span>
    </button>
  {/if}
  {#if supportEnabled}
    <button
      data-nav-level="primary"
      class:active={activeTab === "support"}
      class="attention-wrap"
      type="button"
      aria-label={t("wa_nav_support")}
      title={t("wa_nav_support")}
      onclick={onSupport}
    >
      {#if supportUnreadCount || (supportUnreadLoading && !supportUnreadLoaded)}
        <AttentionDot class="nav-attention-dot" />
      {/if}
      <LifeBuoy size={21} />
      <span class="bottom-nav-label">{t("wa_nav_support")}</span>
    </button>
  {/if}
  <button
    data-nav-level="primary"
    class:active={activeTab === "settings"}
    class="attention-wrap"
    type="button"
    aria-label={t("wa_nav_settings")}
    title={t("wa_nav_settings")}
    onclick={hasUnlinkedIdentity ? onSecurity : onSettings}
  >
    {#if hasUnlinkedIdentity}
      <AttentionDot class="nav-attention-dot" />
    {/if}
    <SettingsIcon size={21} />
    <span class="bottom-nav-label">{t("wa_nav_settings")}</span>
  </button>
  <div class="rail-settings-subnav">
    <button class:active={screen === "security"} type="button" onclick={onSecurity}>
      <ShieldCheck size={18} />
      <span class="bottom-nav-label">{t("wa_security_title", {}, "Security")}</span>
    </button>
    {#if partnerSettingsVisible}
      <button class:active={screen === "partner"} type="button" onclick={onPartner}>
        <Handshake size={18} />
        <span class="bottom-nav-label">{t("wa_nav_partner")}</span>
      </button>
    {/if}
  </div>
  {#if isAdmin}
    <button
      data-nav-level="primary"
      class="rail-admin-entry"
      type="button"
      aria-label={adminLabel}
      title={adminLabel}
      onclick={onAdmin}
    >
      <Shield size={21} />
      <span class="bottom-nav-label">{adminLabel}</span>
    </button>
  {/if}
</nav>

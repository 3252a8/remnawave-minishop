<script lang="ts">
  import type { Snippet } from "svelte";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { UserNavigationItem } from "$lib/webapp/extensionHost";
  import BottomNav from "./BottomNav.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Action = () => void;

  type Props = {
    extensionNavigation?: UserNavigationItem[];
    activeTab?: string;
    brand?: Record<string, unknown>;
    brandTitle?: string;
    bonusesNavigationVisible?: boolean;
    children?: Snippet;
    devicesEnabled?: boolean;
    goDevices: Action;
    goHome: Action;
    goInvite: Action;
    goPartner: Action;
    partnerNavigationVisible?: boolean;
    partnerSettingsVisible?: boolean;
    goSettings: Action;
    goNotifications: Action;
    goSecurity: Action;
    goSupport: Action;
    hasUnlinkedIdentity?: boolean;
    isAdmin?: boolean;
    openAdminPanel: Action;
    screen?: string;
    supportEnabled?: boolean;
    supportUnreadCount?: number;
    supportUnreadLoaded?: boolean;
    supportUnreadLoading?: boolean;
    t: Translate;
  };

  let {
    extensionNavigation = [],
    screen = "home",
    activeTab = "home",
    brand = {},
    brandTitle = "",
    bonusesNavigationVisible = true,
    devicesEnabled = false,
    supportEnabled = true,
    supportUnreadCount = 0,
    supportUnreadLoading = false,
    supportUnreadLoaded = false,
    hasUnlinkedIdentity,
    isAdmin,
    openAdminPanel,
    goDevices,
    goHome,
    goInvite,
    goPartner,
    partnerNavigationVisible = false,
    partnerSettingsVisible = false,
    goSupport,
    goSettings,
    goNotifications,
    goSecurity,
    t,
    children,
  }: Props = $props();
</script>

<div class="phone-screen" class:home-screen={screen === "home"}>
  {#if screen === "install" || screen === "invite" || screen === "partner" || screen === "devices" || screen === "support" || screen === "settings" || screen === "notifications" || screen === "security" || screen === "status"}
    <header class="app-header accent-title">
      <div class="brand-row">
        <BrandMark {brand} />
        <strong>{brandTitle}</strong>
      </div>
    </header>
  {/if}

  {@render children?.()}

  <BottomNav
    {extensionNavigation}
    {activeTab}
    {screen}
    {brand}
    {brandTitle}
    {devicesEnabled}
    {supportEnabled}
    {supportUnreadCount}
    {supportUnreadLoading}
    {supportUnreadLoaded}
    {hasUnlinkedIdentity}
    {isAdmin}
    onAdmin={openAdminPanel}
    onDevices={goDevices}
    onHome={goHome}
    onInvite={goInvite}
    onPartner={goPartner}
    {bonusesNavigationVisible}
    {partnerNavigationVisible}
    {partnerSettingsVisible}
    onSupport={goSupport}
    onSettings={goSettings}
    onNotifications={goNotifications}
    onSecurity={goSecurity}
    {t}
  />
</div>

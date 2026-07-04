<script>
  import {
    Gift,
    Home,
    LifeBuoy,
    Settings as SettingsIcon,
    Shield,
    Smartphone,
  } from "$components/ui/icons.js";
  import { AttentionDot } from "$components/ui/index.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";

  let {
    activeTab = "home",
    brand = {},
    brandTitle = "",
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
    onSupport = () => {},
    onSettings = () => {},
    t = (key) => key,
  } = $props();

  const visibleNavItems = $derived(3 + (devicesEnabled ? 1 : 0) + (supportEnabled ? 1 : 0));
  const adminLabel = $derived(t("wa_settings_admin_panel", {}, "管理后台"));
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
    class:active={activeTab === "home"}
    type="button"
    aria-label={t("wa_nav_home")}
    title={t("wa_nav_home")}
    onclick={onHome}
  >
    <Home size={21} />
    <span class="bottom-nav-label">{t("wa_nav_home")}</span>
  </button>
  <button
    class:active={activeTab === "invite"}
    type="button"
    aria-label={t("wa_nav_bonuses")}
    title={t("wa_nav_bonuses")}
    onclick={onInvite}
  >
    <Gift size={21} />
    <span class="bottom-nav-label">{t("wa_nav_bonuses")}</span>
  </button>
  {#if devicesEnabled}
    <button
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
    class:active={activeTab === "settings"}
    class="attention-wrap"
    type="button"
    aria-label={t("wa_nav_settings")}
    title={t("wa_nav_settings")}
    onclick={onSettings}
  >
    {#if hasUnlinkedIdentity}
      <AttentionDot class="nav-attention-dot" />
    {/if}
    <SettingsIcon size={21} />
    <span class="bottom-nav-label">{t("wa_nav_settings")}</span>
  </button>
  {#if isAdmin}
    <button
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

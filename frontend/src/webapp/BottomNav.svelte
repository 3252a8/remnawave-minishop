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

  export let activeTab = "home";
  export let brand = {};
  export let brandTitle = "";
  export let devicesEnabled = false;
  export let supportEnabled = true;
  export let supportUnreadCount = 0;
  export let supportUnreadLoading = false;
  export let supportUnreadLoaded = false;
  export let hasUnlinkedIdentity = false;
  export let isAdmin = false;
  export let onAdmin = () => {};
  export let onDevices = () => {};
  export let onHome = () => {};
  export let onInvite = () => {};
  export let onSupport = () => {};
  export let onSettings = () => {};
  export let t = (key) => key;

  $: visibleNavItems = 3 + (devicesEnabled ? 1 : 0) + (supportEnabled ? 1 : 0);
  $: adminLabel = t("admin_nav_title", {}, "Админ-панель");
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

<script>
  import {
    Gift,
    Home,
    Settings as SettingsIcon,
    Shield,
    Smartphone,
  } from "$components/ui/icons.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";

  export let activeTab = "home";
  export let brand = {};
  export let brandTitle = "";
  export let devicesEnabled = false;
  export let hasUnlinkedIdentity = false;
  export let isAdmin = false;
  export let onAdmin = () => {};
  export let onDevices = () => {};
  export let onHome = () => {};
  export let onInvite = () => {};
  export let onSettings = () => {};
  export let t = (key) => key;
</script>

<nav class:bottom-nav-devices={devicesEnabled} class="bottom-nav" aria-label={t("wa_navigation")}>
  <div class="rail-brand" aria-hidden="true">
    <BrandMark {brand} />
    <strong>{brandTitle}</strong>
  </div>
  <button class:active={activeTab === "home"} type="button" onclick={onHome}>
    <Home size={21} />
    <span>{t("wa_nav_home")}</span>
  </button>
  <button class:active={activeTab === "invite"} type="button" onclick={onInvite}>
    <Gift size={21} />
    <span>{t("wa_nav_bonuses")}</span>
  </button>
  {#if devicesEnabled}
    <button class:active={activeTab === "devices"} type="button" onclick={onDevices}>
      <Smartphone size={21} />
      <span>{t("wa_nav_devices")}</span>
    </button>
  {/if}
  <button
    class:active={activeTab === "settings"}
    class="attention-wrap"
    type="button"
    onclick={onSettings}
  >
    {#if hasUnlinkedIdentity}
      <span class="attention-dot nav-attention-dot" aria-hidden="true"></span>
    {/if}
    <SettingsIcon size={21} />
    <span>{t("wa_nav_settings")}</span>
  </button>
  {#if isAdmin}
    <button class="rail-admin-entry" type="button" onclick={onAdmin}>
      <Shield size={21} />
      <span>{t("admin_nav_title", {}, "Админ-панель")}</span>
    </button>
  {/if}
</nav>

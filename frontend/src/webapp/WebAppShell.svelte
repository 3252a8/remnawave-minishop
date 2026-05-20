<script>
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import BottomNav from "./BottomNav.svelte";

  export let screen;
  export let activeTab;
  export let brand = {};
  export let brandTitle;
  export let devicesEnabled;
  export let supportEnabled = true;
  export let supportUnreadCount = 0;
  export let supportUnreadLoading = false;
  export let supportUnreadLoaded = false;
  export let hasUnlinkedIdentity;
  export let isAdmin;
  export let openAdminPanel;
  export let goDevices;
  export let goHome;
  export let goInvite;
  export let goSupport;
  export let goSettings;
  export let t;
</script>

<div class="phone-screen" class:home-screen={screen === "home"}>
  {#if screen === "invite" || screen === "devices" || screen === "support" || screen === "settings"}
    <header class="app-header accent-title">
      <div class="brand-row">
        <BrandMark {brand} />
        <strong>{brandTitle}</strong>
      </div>
    </header>
  {/if}

  <slot />

  <BottomNav
    {activeTab}
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
    onSupport={goSupport}
    onSettings={goSettings}
    {t}
  />
</div>

<script>
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import BottomNav from "./BottomNav.svelte";

  export let screen;
  export let activeTab;
  export let brand = {};
  export let brandTitle;
  export let devicesEnabled;
  export let hasUnlinkedIdentity;
  export let isAdmin;
  export let openAdminPanel;
  export let goDevices;
  export let goHome;
  export let goInvite;
  export let goSettings;
  export let t;
</script>

<div class="phone-screen" class:home-screen={screen === "home"}>
  {#if screen === "invite" || screen === "devices" || screen === "settings"}
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
    {hasUnlinkedIdentity}
    {isAdmin}
    onAdmin={openAdminPanel}
    onDevices={goDevices}
    onHome={goHome}
    onInvite={goInvite}
    onSettings={goSettings}
    {t}
  />
</div>

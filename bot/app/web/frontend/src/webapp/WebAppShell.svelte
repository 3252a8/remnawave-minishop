<script>
  import BrandMark from "../BrandMark.svelte";
  import BottomNav from "./BottomNav.svelte";

  export let screen;
  export let activeTab;
  export let CFG;
  export let brandTitle;
  export let brandEmoji;
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
        <BrandMark logoUrl={CFG.logoUrl} emoji={brandEmoji} />
        <strong>{brandTitle}</strong>
      </div>
    </header>
  {/if}

  <slot />

  <BottomNav
    {activeTab}
    {brandTitle}
    {devicesEnabled}
    {hasUnlinkedIdentity}
    {isAdmin}
    logoEmoji={brandEmoji}
    logoUrl={CFG.logoUrl}
    onAdmin={openAdminPanel}
    onDevices={goDevices}
    onHome={goHome}
    onInvite={goInvite}
    onSettings={goSettings}
    {t}
  />
</div>

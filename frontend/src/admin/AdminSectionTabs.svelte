<script lang="ts">
  import type { Snippet } from "svelte";

  import { ADMIN_SECTIONS, adminSectionTabsFor } from "./sections/registry";
  import { requiredFeatureForDescriptor } from "./sections/extensionTypes";
  import type { TranslateFn } from "./sections/user-detail/userDetailTypes";

  type Props = {
    sectionId: string;
    at: TranslateFn;
    availableFeatures: readonly string[];
    featuresResolved: boolean;
    routePrefix: string;
    onNavigateSection: (sectionId: string) => void;
    onOpenUserCard: (userId: number) => void;
    section: Snippet;
  };

  let {
    sectionId,
    at,
    availableFeatures,
    featuresResolved,
    routePrefix,
    onNavigateSection,
    onOpenUserCard,
    section,
  }: Props = $props();

  const featureSet = $derived(new Set(availableFeatures));
  const tabs = $derived(adminSectionTabsFor(sectionId, featureSet));
  const sectionLabel = $derived.by(() => {
    const descriptor = ADMIN_SECTIONS.find((item) => item.id === sectionId);
    return descriptor ? at(descriptor.titleI18nKey, {}, descriptor.fallbackTitle) : sectionId;
  });

  // "" is the host section itself, which always stays the first tab.
  let activeTab = $state("");
  let lastSectionId = "";

  $effect(() => {
    if (sectionId === lastSectionId) return;
    lastSectionId = sectionId;
    activeTab = "";
  });

  // An extension can disappear when its license lapses mid-session; fall back
  // to the host section instead of rendering nothing.
  $effect(() => {
    if (activeTab && !tabs.some((tab) => tab.id === activeTab)) activeTab = "";
  });

  const activeDescriptor = $derived(tabs.find((tab) => tab.id === activeTab) ?? null);
</script>

{#if tabs.length}
  <div class="admin-tabs admin-section-tabs" role="tablist" aria-label={sectionLabel}>
    <button
      type="button"
      role="tab"
      class:active={activeTab === ""}
      aria-selected={activeTab === ""}
      onclick={() => (activeTab = "")}
    >
      {sectionLabel}
    </button>
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        role="tab"
        class:active={activeTab === tab.id}
        aria-selected={activeTab === tab.id}
        onclick={() => (activeTab = tab.id)}
      >
        {at(tab.i18nKey, {}, tab.fallbackLabel)}
      </button>
    {/each}
  </div>
{/if}

{#if activeDescriptor}
  {@const TabComponent = activeDescriptor.component}
  {@const requiredFeature = requiredFeatureForDescriptor(activeDescriptor)}
  <div
    role="tabpanel"
    aria-label={at(activeDescriptor.i18nKey, {}, activeDescriptor.fallbackLabel)}
  >
    <TabComponent
      runtimeViewId={activeDescriptor.runtimeViewId}
      runtimeEntry={activeDescriptor.runtimeEntry}
      {at}
      {availableFeatures}
      {featuresResolved}
      {routePrefix}
      {onNavigateSection}
      {onOpenUserCard}
      featureAvailable={!requiredFeature || featureSet.has(requiredFeature)}
    />
  </div>
{:else}
  {@render section()}
{/if}

<style>
  .admin-section-tabs {
    margin-bottom: 14px;
  }
</style>

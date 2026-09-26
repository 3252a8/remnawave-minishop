<script lang="ts">
  import { onMount, type Snippet } from "svelte";
  import { Tabs } from "$components/ui/primitives.js";
  import AdminExtensionPoint from "./sections/AdminExtensionPoint.svelte";
  import { adminExtensionRevision } from "./sections/extensionRegistry";
  import { selectExtensionTab } from "$lib/extensions/composition";

  import { ADMIN_SECTIONS, adminSectionTabsFor } from "./sections/registry";
  import { requiredFeatureForDescriptor } from "./sections/extensionTypes";
  import type { TranslateFn } from "./sections/user-detail/userDetailTypes";

  type Props = {
    sectionId: string;
    currentLang: string;
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
    currentLang,
    at,
    availableFeatures,
    featuresResolved,
    routePrefix,
    onNavigateSection,
    onOpenUserCard,
    section,
  }: Props = $props();

  const featureSet = $derived(new Set(availableFeatures));
  const tabs = $derived.by(() => {
    void $adminExtensionRevision;
    return adminSectionTabsFor(sectionId, featureSet);
  });
  const sectionLabel = $derived.by(() => {
    const descriptor = ADMIN_SECTIONS.find((item) => item.id === sectionId);
    return descriptor ? at(descriptor.titleI18nKey, {}, descriptor.fallbackTitle) : sectionId;
  });

  // "" is the host section itself, which always stays the first tab.
  let search = $state(window.location.search);
  const activeTab = $derived(selectExtensionTab(tabs, search));

  function selectTab(id: string) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("extensionTab", id);
    else url.searchParams.delete("extensionTab");
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  onMount(() => {
    const update = () => {
      search = window.location.search;
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  });

  const activeDescriptor = $derived(tabs.find((tab) => tab.id === activeTab) ?? null);
</script>

<Tabs.Root value={activeTab} onValueChange={selectTab}>
  {#if tabs.length}
    <Tabs.List class="admin-tabs-list admin-section-tabs" aria-label={sectionLabel}>
      <Tabs.Trigger value="" class="admin-tabs-trigger">
        {sectionLabel}
      </Tabs.Trigger>
      {#each tabs as tab (tab.id)}
        <Tabs.Trigger value={tab.id} class="admin-tabs-trigger">
          {at(tab.i18nKey, {}, tab.fallbackLabel)}
        </Tabs.Trigger>
      {/each}
    </Tabs.List>
  {/if}

  {#if activeDescriptor}
    {@const TabComponent = activeDescriptor.component}
    {@const requiredFeature = requiredFeatureForDescriptor(activeDescriptor)}
    <Tabs.Content value={activeDescriptor.id}>
      {#key `${activeDescriptor.id}:${activeDescriptor.runtimeDigest || ""}`}
        <TabComponent
          runtimeViewId={activeDescriptor.runtimeViewId}
          runtimeEntry={activeDescriptor.runtimeEntry}
          {at}
          {currentLang}
          context={{ sectionId, tabId: activeDescriptor.id }}
          {availableFeatures}
          {featuresResolved}
          {routePrefix}
          {onNavigateSection}
          {onOpenUserCard}
          featureAvailable={!requiredFeature || featureSet.has(requiredFeature)}
        />
      {/key}
    </Tabs.Content>
  {:else}
    <Tabs.Content value="">
      <AdminExtensionPoint target={`admin.${sectionId}.content`}
        >{@render section()}</AdminExtensionPoint
      >
    </Tabs.Content>
  {/if}
</Tabs.Root>

<style>
  :global(.admin-section-tabs) {
    margin-bottom: 14px;
  }
</style>

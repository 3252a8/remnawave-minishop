<script lang="ts">
  import type { Snippet } from "svelte";
  import { requiredFeatureForDescriptor, type AdminUiSlotDescriptor } from "./extensionTypes";
  import type { AdminCompositionContext } from "./compositionContext";
  import PluginHost from "./PluginHost.svelte";
  let {
    descriptor,
    composition,
    children,
  }: {
    descriptor: AdminUiSlotDescriptor;
    composition: AdminCompositionContext;
    children?: Snippet;
  } = $props();
  let status = $state<"loading" | "ready" | "failed">("loading");
  const viewProps = $derived({
    ...composition,
    featureAvailable:
      !requiredFeatureForDescriptor(descriptor) ||
      composition.availableFeatures.includes(requiredFeatureForDescriptor(descriptor)),
  });
  $effect(() => {
    if (descriptor.component !== PluginHost && status === "loading") status = "ready";
  });
</script>

<section
  class="admin-extension-content"
  aria-label={composition.at(descriptor.i18nKey, {}, descriptor.fallbackLabel)}
>
  {#if descriptor.component === PluginHost}
    <PluginHost
      {...viewProps}
      runtimeViewId={descriptor.runtimeViewId}
      runtimeEntry={descriptor.runtimeEntry}
      bind:status
    />
  {:else}
    {@const View = descriptor.component}
    <svelte:boundary
      onerror={() => {
        status = "failed";
      }}
    >
      <View {...viewProps} />
      {#snippet failed()}
        <p role="alert">{composition.at("plugin_view_failed")}</p>
      {/snippet}
    </svelte:boundary>
  {/if}
</section>
{#if status !== "ready"}{@render children?.()}{/if}

<style>
  .admin-extension-content {
    min-width: 0;
    margin-block: 1rem;
  }
</style>

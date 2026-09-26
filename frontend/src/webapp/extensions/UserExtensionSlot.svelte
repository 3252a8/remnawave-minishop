<script lang="ts">
  import type { Snippet } from "svelte";
  import type { UserExtensionPlugin, UserExtensionView } from "$lib/webapp/extensionHost";
  import type { UserCompositionContext } from "./compositionContext";
  import UserPluginHost from "./UserPluginHost.svelte";

  let {
    plugin,
    view,
    composition,
    children,
  }: {
    plugin: UserExtensionPlugin;
    view: UserExtensionView;
    composition: UserCompositionContext;
    children?: Snippet;
  } = $props();
  let status = $state<"loading" | "ready" | "failed">("loading");
</script>

{#if composition.client}
  <section
    class="extension-content"
    aria-label={view.i18nKey ? composition.t(view.i18nKey, {}, view.label) : view.label}
  >
    <UserPluginHost
      {plugin}
      {view}
      client={composition.client}
      t={composition.t}
      language={composition.language}
      routePrefix={composition.routePrefix}
      context={{
        ...composition.context,
        target: view.target,
        viewId: view.id,
        parent: view.parent,
      }}
      bind:status
    />
  </section>
{/if}
{#if status !== "ready"}{@render children?.()}{/if}

<style>
  .extension-content {
    display: grid;
    gap: 1rem;
    min-width: 0;
    margin-block: 1rem;
  }
</style>

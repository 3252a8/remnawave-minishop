<script lang="ts">
  import { getContext, type Snippet } from "svelte";
  import { composeUi } from "$lib/extensions/composition";
  import { ADMIN_UI_SLOTS, adminExtensionRevision } from "./extensionRegistry";
  import { isFeatureBoundDescriptorVisible, requiredFeatureForDescriptor } from "./extensionTypes";
  import { ADMIN_COMPOSITION, type AdminCompositionContext } from "./compositionContext";
  import AdminExtensionSlot from "./AdminExtensionSlot.svelte";

  let {
    target,
    context = {},
    children,
  }: {
    target: string;
    context?: Record<string, unknown>;
    children?: Snippet;
  } = $props();
  const host = getContext<AdminCompositionContext | undefined>(ADMIN_COMPOSITION);
  const composition = $derived(
    host
      ? {
          ...host,
          context: { ...host.context, ...context, target },
        }
      : null
  );
  const content = $derived.by(() => {
    void $adminExtensionRevision;
    const features = new Set(host?.availableFeatures || []);
    return composeUi(
      ADMIN_UI_SLOTS.filter(
        (slot) =>
          isFeatureBoundDescriptorVisible(slot, features) &&
          (slot.placement !== "replace" ||
            (target !== "admin.plugins.content" &&
              target !== "admin.users.detail.actions" &&
              (!requiredFeatureForDescriptor(slot) ||
                features.has(requiredFeatureForDescriptor(slot)))))
      ),
      target
    );
  });
</script>

{#if composition}
  {#each content.before as descriptor (`${descriptor.id}:${descriptor.runtimeDigest || ""}`)}
    <AdminExtensionSlot {descriptor} {composition} />
  {/each}
  {#if content.conflict}<p role="alert">{composition.at("plugin_view_conflict")}</p>{/if}
  {#if content.replacement}
    {#key `${content.replacement.id}:${content.replacement.runtimeDigest || ""}`}
      <AdminExtensionSlot descriptor={content.replacement} {composition} {children} />
    {/key}
  {:else}{@render children?.()}{/if}
  {#each content.after as descriptor (`${descriptor.id}:${descriptor.runtimeDigest || ""}`)}
    <AdminExtensionSlot {descriptor} {composition} />
  {/each}
{:else}{@render children?.()}{/if}

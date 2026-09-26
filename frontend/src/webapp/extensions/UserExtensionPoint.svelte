<script lang="ts">
  import { getContext, type Snippet } from "svelte";
  import { composeUi } from "$lib/extensions/composition";
  import { USER_COMPOSITION, type UserCompositionContext } from "./compositionContext";
  import UserExtensionSlot from "./UserExtensionSlot.svelte";

  let { target, children }: { target: string; children?: Snippet } = $props();
  const composition = getContext<UserCompositionContext | undefined>(USER_COMPOSITION);
  const content = $derived(
    composeUi(
      (composition?.plugins || []).flatMap((plugin) =>
        (plugin.views || [])
          .filter(
            (view) =>
              view.target !== "page" &&
              !(view.target === "user.security.content" && view.placement === "replace")
          )
          .map((view) => ({ ...view, id: `${plugin.id}:${view.id}`, plugin, view }))
      ),
      target
    )
  );
</script>

{#if composition}
  {#each content.before as item (`${item.id}:${item.plugin.digest}`)}
    <UserExtensionSlot plugin={item.plugin} view={item.view} {composition} />
  {/each}
  {#if content.conflict}<p role="alert">{composition.t("wa_extension_conflict")}</p>{/if}
  {#if content.replacement}
    {#key `${content.replacement.id}:${content.replacement.plugin.digest}`}
      <UserExtensionSlot
        plugin={content.replacement.plugin}
        view={content.replacement.view}
        {composition}
        {children}
      />
    {/key}
  {:else}{@render children?.()}{/if}
  {#each content.after as item (`${item.id}:${item.plugin.digest}`)}
    <UserExtensionSlot plugin={item.plugin} view={item.view} {composition} />
  {/each}
{:else}{@render children?.()}{/if}

<script lang="ts">
  import { getThemesStore } from "$lib/admin/context";
  import type { ThemeInstallation } from "$lib/admin/stores/themeLibraryStore.svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Dialog } from "$components/ui/index.js";
  import AppearanceEffectsConsent from "./AppearanceEffectsConsent.svelte";
  import AppearanceEffectsPreview from "./AppearanceEffectsPreview.svelte";
  let {
    item,
    at,
  }: {
    item: ThemeInstallation;
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  } = $props();
  const library = getThemesStore().library;
  let open = $state(false);
  let accepted = $state(false);
</script>

<AdminButton
  size="sm"
  disabled={library.busy}
  onclick={() => {
    accepted = false;
    open = true;
  }}
>
  {at(
    item.effects_enabled ? "theme_effects_enabled" : "theme_effects_disabled",
    {},
    item.effects_enabled ? "JavaScript: enabled" : "JavaScript: disabled"
  )}
</AdminButton>
<Dialog
  portal
  {open}
  title={at("theme_effects_title", {}, "JavaScript effects")}
  closeLabel={at("theme_effects_close", {}, "Close")}
  onclose={() => (open = false)}
>
  <AppearanceEffectsPreview themeKey={item.key} {at} />
  <AppearanceEffectsConsent
    {at}
    checked={accepted}
    disabled={library.busy}
    onchange={(value) => (accepted = value)}
  />
  <AdminButton
    disabled={!accepted || library.busy}
    onclick={async () => {
      await library.setEffects(item, true);
      if (!library.error) open = false;
    }}>{at("theme_effects_enable", {}, "Allow effects")}</AdminButton
  >
  <AdminButton
    variant="default"
    disabled={library.busy}
    onclick={async () => {
      await library.setEffects(item, false);
      if (!library.error) open = false;
    }}>{at("theme_effects_disable", {}, "Disable effects")}</AdminButton
  >
</Dialog>

<script lang="ts">
  import { getSettingsStore, getTariffsStore } from "$lib/admin/context";
  import type { SettingsDirtyState } from "$lib/admin/tariffSettings";
  import type { SettingField, SettingsSection } from "$lib/admin/stores/settingsStore";
  import { onMount } from "svelte";
  import TariffReferralSettings from "../../tariffs/TariffReferralSettings.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at }: { at: TranslateFn } = $props();

  const settingsStore = getSettingsStore();
  const tariffsStore = getTariffsStore();
  const settingsSections: SettingsSection[] = $derived(settingsStore.settingsSections || []);
  const settingsDirty: SettingsDirtyState = $derived(settingsStore.settingsDirty || {});
  const settingsFieldMap: Map<string, SettingField> = $derived(
    new Map(
      settingsSections.flatMap((section) => section.fields || []).map((field) => [field.key, field])
    )
  );

  // No `loadSettings()` here: the settings screen already loads them, and it
  // hides the accordion while loading. Re-requesting on mount unmounts this
  // component, which remounts and requests again — the panel never settles.
  onMount(() => {
    void tariffsStore.loadTariffs();
  });
</script>

<!-- Only the referral settings themselves. Per-tariff bonus days stay in the
     tariff editor, and the screen header owns the single Save. -->
<TariffReferralSettings {at} {settingsDirty} {settingsFieldMap} standalone />

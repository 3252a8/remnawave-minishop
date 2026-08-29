<script lang="ts">
  import IconPickerDialog from "./IconPickerDialog.svelte";
  import type { ComponentType, SvelteComponent } from "svelte";
  import type { AdminSettingField } from "$lib/admin/settingsSections";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  let {
    at,
    iconPickerField = null,
    iconPickerSearch = $bindable(""),
    filteredIconOptions = [],
    fieldLabelText,
    iconComponent,
    iconValue,
    iconLabel,
    iconIsDefault,
    closeIconPicker,
    clearIconPickerField,
    selectIcon,
  }: {
    at: TranslateFn;
    iconPickerField?: AdminSettingField | null;
    iconPickerSearch?: string;
    filteredIconOptions?: readonly string[];
    fieldLabelText: (field: AdminSettingField) => string;
    iconComponent: (name: unknown) => DynamicComponent | null;
    iconValue: (field: AdminSettingField | null) => string;
    iconLabel: (field: AdminSettingField | null) => string;
    iconIsDefault: (field: AdminSettingField) => boolean;
    closeIconPicker: () => void;
    clearIconPickerField: () => void;
    selectIcon: (name: string) => void;
  } = $props();
</script>

<IconPickerDialog
  {at}
  open={Boolean(iconPickerField)}
  description={iconPickerField ? fieldLabelText(iconPickerField) : ""}
  bind:search={iconPickerSearch}
  options={filteredIconOptions}
  currentIconName={iconValue(iconPickerField)}
  currentIconLabel={iconLabel(iconPickerField)}
  isDefault={iconPickerField ? iconIsDefault(iconPickerField) : true}
  {iconComponent}
  onClose={closeIconPicker}
  onUseDefault={clearIconPickerField}
  onSelect={selectIcon}
/>

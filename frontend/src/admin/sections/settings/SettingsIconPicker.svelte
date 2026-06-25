<script lang="ts">
  import { Input, ScrollArea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Search, X } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
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

<Dialog
  open={Boolean(iconPickerField)}
  title={at("settings_icon_picker_title", {}, "Choose icon")}
  description={iconPickerField ? fieldLabelText(iconPickerField) : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={closeIconPicker}
  class="admin-icon-picker-dialog"
>
  <div class="admin-icon-picker-body">
    {#if iconPickerField}
      {@const currentIconName = iconValue(iconPickerField)}
      {@const CurrentIcon = iconComponent(currentIconName)}
      <div class="admin-icon-picker-current">
        <span class="admin-icon-picker-current-preview" aria-hidden="true">
          {#if CurrentIcon}
            <CurrentIcon size={24} />
          {/if}
        </span>
        <span class="admin-icon-picker-current-meta">
          <small>{at("settings_icon_current", {}, "Current icon")}</small>
          <strong>{iconLabel(iconPickerField)}</strong>
        </span>
        {#if !iconIsDefault(iconPickerField)}
          <AdminButton size="sm" variant="ghost" onclick={clearIconPickerField}>
            <X size={12} />
            {at("settings_icon_use_default", {}, "Use default")}
          </AdminButton>
        {/if}
      </div>
    {/if}
    <div class="admin-icon-picker-toolbar">
      <label class="admin-icon-picker-search">
        <Search size={15} />
        <Input
          bind:value={iconPickerSearch}
          class="input"
          type="text"
          placeholder={at("search", {}, "Search")}
        />
      </label>
    </div>
    <ScrollArea class="admin-icon-picker-scroll" maxHeight="min(52vh, 460px)">
      <div class="admin-icon-picker-grid">
        {#each filteredIconOptions as iconName}
          {@const Icon = iconComponent(iconName)}
          <button
            class:active={iconPickerField && iconValue(iconPickerField) === iconName}
            class="admin-icon-picker-option"
            type="button"
            onclick={() => selectIcon(iconName)}
          >
            {#if Icon}
              <Icon size={18} />
            {/if}
            <span>{iconName}</span>
          </button>
        {/each}
      </div>
    </ScrollArea>
  </div>
</Dialog>

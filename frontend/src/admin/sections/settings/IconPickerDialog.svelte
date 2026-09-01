<script lang="ts">
  import { Input, ScrollArea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Search, X } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type { ComponentType, SvelteComponent } from "svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  let {
    at,
    open = false,
    description = "",
    search = $bindable(""),
    options = [],
    currentIconName = "",
    currentIconLabel = "",
    isDefault = true,
    iconComponent,
    onClose,
    onUseDefault,
    onSelect,
  }: {
    at: TranslateFn;
    open?: boolean;
    description?: string;
    search?: string;
    options?: readonly string[];
    currentIconName?: string;
    currentIconLabel?: string;
    isDefault?: boolean;
    iconComponent: (name: unknown) => DynamicComponent | null;
    onClose: () => void;
    onUseDefault: () => void;
    onSelect: (name: string) => void;
  } = $props();
</script>

<Dialog
  {open}
  title={at("settings_icon_picker_title", {}, "Choose icon")}
  {description}
  closeLabel={at("close", {}, "Close")}
  onclose={onClose}
  class="admin-icon-picker-dialog"
>
  {#if open}
    {@const CurrentIcon = iconComponent(currentIconName)}
    <div class="admin-icon-picker-body">
      <div class="admin-icon-picker-current">
        <span class="admin-icon-picker-current-preview" aria-hidden="true">
          {#if CurrentIcon}
            <CurrentIcon size={24} />
          {/if}
        </span>
        <span class="admin-icon-picker-current-meta">
          <small>{at("settings_icon_current", {}, "Current icon")}</small>
          <strong>{currentIconLabel}</strong>
        </span>
        {#if !isDefault}
          <AdminButton size="sm" variant="ghost" onclick={onUseDefault}>
            <X size={12} />
            {at("settings_icon_use_default", {}, "Use default")}
          </AdminButton>
        {/if}
      </div>
      <div class="admin-icon-picker-toolbar">
        <label class="admin-icon-picker-search">
          <Search size={15} />
          <Input
            bind:value={search}
            class="input"
            type="text"
            placeholder={at("search", {}, "Search")}
          />
        </label>
      </div>
      <ScrollArea class="admin-icon-picker-scroll" maxHeight="min(52vh, 460px)">
        <div class="admin-icon-picker-grid">
          {#each options as iconName}
            {@const Icon = iconComponent(iconName)}
            <button
              class:active={currentIconName === iconName}
              class="admin-icon-picker-option"
              type="button"
              onclick={() => onSelect(iconName)}
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
  {/if}
</Dialog>

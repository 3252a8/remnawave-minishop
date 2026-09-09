<script lang="ts">
  import { Check, ChevronsUpDown, Paintbrush } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";
  import type { ThemeOption } from "$lib/webapp/themePreference.js";

  let {
    open = $bindable(false),
    value = "auto",
    options = [],
    label = "Theme mode",
    onOpenChange = () => {},
    onValueChange = () => {},
  }: {
    open?: boolean;
    value?: string;
    options?: ThemeOption[];
    label?: string;
    onOpenChange?: (open: boolean) => void;
    onValueChange?: (value: string) => void;
  } = $props();

  const selectContentProps = { trapFocus: false } as Record<string, unknown>;
  const currentOption = $derived(options.find((option) => option.value === value) || options[0]);
</script>

<div class="settings-row settings-row-language settings-row-theme">
  <Paintbrush size={21} />
  <Select.Root type="single" bind:open {value} items={options} {onOpenChange} {onValueChange}>
    <Select.Trigger class="language-select-trigger theme-select-trigger" aria-label={label}>
      <span class="language-select-copy">
        <strong>{label}</strong>
        <small class="language-select-current">{currentOption?.label || value}</small>
      </span>
      <ChevronsUpDown size={16} />
    </Select.Trigger>
    <Select.Content
      class="language-select-content theme-select-content"
      side="bottom"
      align="end"
      sideOffset={6}
      {...selectContentProps}
    >
      <Select.Viewport class="language-select-viewport">
        {#each options as option (option.value)}
          <Select.Item value={option.value} label={option.label} class="language-select-item">
            <span class="language-select-item-main"><span>{option.label}</span></span>
            <Check size={15} class="language-select-item-check" />
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Root>
</div>

<style>
  :global(.theme-select-content) {
    min-width: 180px;
  }
</style>

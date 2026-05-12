<script>
  import { Check, ChevronsUpDown, Globe2 } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";

  export let open = false;
  export let value = "ru";
  export let currentOption = null;
  export let userLanguage = "";
  export let options = [];
  export let disabled = false;
  export let clickGuard = false;
  export let clickGuardArmed = false;
  export let closeLabel = "Close";
  export let label = "Language";
  export let onOpenChange = () => {};
  export let onValueChange = () => {};

  function closeFromGuard(event) {
    event.preventDefault();
    event.stopPropagation();
    if (clickGuardArmed) onOpenChange(false);
  }
</script>

{#if open || clickGuard}
  <button
    class="language-select-guard"
    class:language-select-guard--armed={clickGuardArmed}
    type="button"
    aria-label={closeLabel}
    onpointerdown={closeFromGuard}
    onclick={closeFromGuard}
  ></button>
{/if}

<div class="settings-row settings-row-language">
  <Globe2 size={21} />
  <Select.Root
    type="single"
    bind:open
    {value}
    items={options}
    {disabled}
    onOpenChange={onOpenChange}
    onValueChange={onValueChange}
  >
    <Select.Trigger class="language-select-trigger" aria-label={label}>
      <span class="language-select-copy">
        <strong>{label}</strong>
        <small class="language-select-current">
          <span class="emoji-flag" aria-hidden="true">{currentOption?.flag || "🏳️"}</span>
          {currentOption?.label || userLanguage}
        </small>
      </span>
      <ChevronsUpDown size={16} />
    </Select.Trigger>
    <Select.Content class="language-select-content" side="bottom" align="end" sideOffset={6}>
      <Select.Viewport class="language-select-viewport">
        {#each options as option (option.value)}
          <Select.Item value={option.value} label={option.label} class="language-select-item">
            <span class="language-select-item-main">
              <span class="emoji-flag" aria-hidden="true">{option.flag}</span>
              <span>{option.label}</span>
            </span>
            <Check size={15} class="language-select-item-check" />
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Root>
</div>

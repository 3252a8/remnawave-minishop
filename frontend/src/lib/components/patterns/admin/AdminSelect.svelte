<script lang="ts">
  import { Check, ChevronDown, LockKeyhole } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";

  type SelectItem = {
    value: string;
    label: string;
    disabled?: boolean;
    locked?: boolean;
    group?: string;
  };
  type Props = {
    value?: string;
    items?: SelectItem[];
    ariaLabel?: string;
    placeholder?: string;
    disabled?: boolean;
    side?: "bottom" | "left" | "right" | "top";
    align?: "center" | "end" | "start";
    sideOffset?: number;
    collisionPadding?: number;
    onValueChange?: (value: string) => void;
    class?: string;
  };

  let {
    value = $bindable(""),
    items = [],
    ariaLabel = "",
    placeholder = "",
    disabled = false,
    side = "bottom",
    align = "start",
    sideOffset = 6,
    collisionPadding = 12,
    onValueChange = () => {},
    class: className = "",
  }: Props = $props();

  const selected = $derived(items.find((item) => item.value === value));

  function handleValueChange(next: string) {
    value = next;
    onValueChange(next);
  }
</script>

<Select.Root type="single" {value} {items} {disabled} onValueChange={handleValueChange}>
  <Select.Trigger
    class={`admin-select-trigger ${className}`.trim()}
    aria-label={ariaLabel || placeholder}
  >
    <span>{selected?.label || placeholder}</span>
    <ChevronDown size={14} class="admin-select-icon" />
  </Select.Trigger>
  <Select.Portal>
    <Select.Content class="admin-select-content" {side} {align} {sideOffset} {collisionPadding}>
      <Select.Viewport class="admin-select-viewport">
        {#each items as item, index (item.value)}
          {#if item.group && item.group !== items[index - 1]?.group}
            <div class="admin-select-group-label" aria-hidden="true">{item.group}</div>
          {/if}
          <Select.Item
            value={item.value}
            label={item.label}
            disabled={item.disabled}
            class="admin-select-item"
          >
            <span>{item.label}</span>
            {#if item.locked}
              <LockKeyhole size={14} class="admin-select-item-lock" />
            {/if}
            <Check size={14} class="admin-select-item-check" />
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>

<style>
  .admin-select-group-label {
    color: var(--muted-foreground, currentColor);
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.5rem 0.625rem 0.25rem;
  }

  :global(.admin-select-item-lock) {
    margin-left: auto;
    opacity: 0.7;
  }
</style>

<script lang="ts">
  import { Check, ChevronDown, LockKeyhole } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";
  import { dynamicComponent } from "$lib/../admin/adminLazyComponents";
  import { SELECT_ITEM_ICONS, type SelectItemIcon } from "./selectItemIcons";

  type SelectItem = {
    value: string;
    label: string;
    disabled?: boolean;
    locked?: boolean;
    group?: string;
    /** Neutral icon name; an unknown name simply renders no glyph. */
    icon?: SelectItemIcon | string;
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

  function iconFor(name: string | undefined): unknown {
    return name ? SELECT_ITEM_ICONS[name] : undefined;
  }

  const selectedIcon = $derived(iconFor(selected?.icon));
  let safeAreaPadding = $state<{
    top: number;
    right: number;
    bottom: number;
    left: number;
  } | null>(null);
  const effectiveCollisionPadding = $derived(
    safeAreaPadding
      ? {
          top: collisionPadding + safeAreaPadding.top,
          right: collisionPadding + safeAreaPadding.right,
          bottom: collisionPadding + safeAreaPadding.bottom,
          left: collisionPadding + safeAreaPadding.left,
        }
      : collisionPadding
  );

  function updateCollisionPadding(open: boolean) {
    if (!open) return;
    const screen = document.querySelector<HTMLElement>(".admin-screen-wrap");
    if (!screen) return;
    const style = getComputedStyle(screen);
    safeAreaPadding = {
      top: Number.parseFloat(style.paddingTop || "0"),
      right: Number.parseFloat(style.paddingRight || "0"),
      bottom: Number.parseFloat(style.paddingBottom || "0"),
      left: Number.parseFloat(style.paddingLeft || "0"),
    };
  }

  function handleValueChange(next: string) {
    value = next;
    onValueChange(next);
  }
</script>

<Select.Root
  type="single"
  {value}
  {items}
  {disabled}
  onOpenChange={updateCollisionPadding}
  onValueChange={handleValueChange}
>
  <Select.Trigger
    class={`admin-select-trigger ${className}`.trim()}
    aria-label={ariaLabel || placeholder}
  >
    {#if selectedIcon}
      {@const SelectedIcon = dynamicComponent(selectedIcon)}
      <SelectedIcon size={14} class="admin-select-item-icon" />
    {/if}
    <span>{selected?.label || placeholder}</span>
    <ChevronDown size={14} class="admin-select-icon" />
  </Select.Trigger>
  <Select.Portal>
    <Select.Content
      class="admin-select-content"
      {side}
      {align}
      {sideOffset}
      collisionPadding={effectiveCollisionPadding}
    >
      <Select.Viewport class="admin-select-viewport">
        {#each items as item, index (item.value)}
          {#if item.group && item.group !== items[index - 1]?.group}
            <div class="admin-select-group-label" aria-hidden="true">{item.group}</div>
          {/if}
          {@const itemIcon = iconFor(item.icon)}
          <Select.Item
            value={item.value}
            label={item.label}
            disabled={item.disabled}
            class="admin-select-item"
          >
            {#if itemIcon}
              {@const ItemIcon = dynamicComponent(itemIcon)}
              <ItemIcon size={14} class="admin-select-item-icon" />
            {/if}
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
  /* A group reads as a section: the caption is paired with a hairline that
     runs to the edge, and every group after the first is separated from the
     items above it. */
  .admin-select-group-label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--admin-muted, currentColor);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.5rem 0.625rem 0.3rem;
  }

  .admin-select-group-label::after {
    content: "";
    flex: 1 1 auto;
    height: 1px;
    background: var(--admin-border, currentColor);
  }

  .admin-select-group-label:not(:first-child) {
    margin-top: 4px;
    border-top: 1px solid var(--admin-border, currentColor);
    padding-top: 0.6rem;
  }

  :global(.admin-select-item-lock) {
    margin-left: auto;
    opacity: 0.7;
  }

  :global(.admin-select-item-icon) {
    flex: 0 0 auto;
    opacity: 0.85;
  }
</style>

<script lang="ts">
  import { onDestroy } from "svelte";
  import { controlSizeClass, type ControlSize } from "$components/ui/controlSize";

  import { Combobox } from "$components/ui/primitives.js";
  import { Check, ChevronDown } from "$components/ui/icons.js";

  type ComboboxItem = {
    value: string;
    label: string;
    disabled?: boolean;
    group?: string;
  };
  type Props = {
    value?: string;
    items?: ComboboxItem[];
    ariaLabel?: string;
    placeholder?: string;
    emptyMessage?: string;
    loadingMessage?: string;
    loading?: boolean;
    disabled?: boolean;
    maxLength?: number;
    searchDelay?: number;
    onValueChange?: (value: string) => void;
    onInputChange?: (value: string) => void;
    class?: string;
    controlSize?: ControlSize;
  };

  let {
    value = "",
    items = [],
    ariaLabel = "",
    placeholder = "",
    emptyMessage = "No matches",
    loadingMessage = "Loading...",
    loading = false,
    disabled = false,
    maxLength,
    searchDelay = 220,
    onValueChange = () => {},
    onInputChange = () => {},
    class: className = "",
    controlSize,
  }: Props = $props();

  let open = $state(false);
  let inputQuery = $state("");
  let searchTimer: ReturnType<typeof setTimeout> | null = null;

  const visibleItems = $derived.by(() => {
    const query = inputQuery.trim().toLocaleLowerCase();
    if (!query) return items;
    return items.filter(
      (item) =>
        item.value.toLocaleLowerCase().includes(query) ||
        item.label.toLocaleLowerCase().includes(query)
    );
  });

  $effect(() => {
    inputQuery = value;
  });

  onDestroy(() => {
    if (searchTimer) clearTimeout(searchTimer);
  });

  function requestSuggestions(next: string): void {
    if (searchTimer) clearTimeout(searchTimer);
    if (!next.trim()) {
      onInputChange("");
      return;
    }
    searchTimer = setTimeout(() => {
      searchTimer = null;
      onInputChange(next);
    }, searchDelay);
  }

  function handleInput(event: Event): void {
    const next = (event.currentTarget as HTMLInputElement).value;
    inputQuery = next;
    onValueChange(next);
    requestSuggestions(next);
  }

  function handleValueChange(next: string): void {
    inputQuery = next;
    onValueChange(next);
  }
</script>

<Combobox.Root
  type="single"
  {value}
  inputValue={value}
  items={visibleItems}
  {disabled}
  allowDeselect={false}
  bind:open
  onValueChange={handleValueChange}
>
  <div
    class={`admin-combobox ${controlSizeClass(controlSize)} ${className}`.trim()}
    data-control-size={controlSize}
  >
    <Combobox.Input
      class={`admin-combobox-input ${controlSizeClass(controlSize)}`.trim()}
      data-control-size={controlSize}
      aria-label={ariaLabel || placeholder}
      {placeholder}
      maxlength={maxLength}
      autocomplete="off"
      autocapitalize="characters"
      spellcheck={false}
      onfocus={() => (open = true)}
      oninput={handleInput}
    />
    <Combobox.Trigger
      class="admin-combobox-trigger"
      aria-label={ariaLabel || placeholder}
      tabindex={-1}
    >
      <ChevronDown
        size={14}
        class={`admin-select-icon${open ? " admin-combobox-icon-open" : ""}`}
      />
    </Combobox.Trigger>
  </div>
  <Combobox.Portal>
    <Combobox.Content
      class="admin-select-content admin-combobox-content"
      side="bottom"
      align="start"
      sideOffset={6}
      collisionPadding={12}
    >
      <Combobox.Viewport class="admin-select-viewport">
        {#each visibleItems as item, index (item.value)}
          {#if item.group && item.group !== visibleItems[index - 1]?.group}
            <div class="admin-combobox-group-label" aria-hidden="true">{item.group}</div>
          {/if}
          <Combobox.Item
            value={item.value}
            label={item.label}
            disabled={item.disabled}
            class="admin-select-item"
          >
            <span>{item.label}</span>
            <Check size={14} class="admin-select-item-check" />
          </Combobox.Item>
        {/each}
        {#if loading}
          <div class="admin-combobox-status" aria-live="polite">{loadingMessage}</div>
        {:else if !visibleItems.length}
          <div class="admin-combobox-status" aria-live="polite">{emptyMessage}</div>
        {/if}
      </Combobox.Viewport>
    </Combobox.Content>
  </Combobox.Portal>
</Combobox.Root>

<style>
  .admin-combobox {
    position: relative;
    width: 100%;
    min-width: 0;
  }

  .admin-combobox :global(.admin-combobox-input) {
    display: block;
    width: 100%;
    height: 36px;
    padding: 0 var(--ui-control-height, 36px) 0 12px;
    border: 1px solid var(--admin-border-strong);
    border-radius: 10px;
    background: color-mix(in srgb, var(--admin-bg) 82%, var(--admin-surface-2));
    color: var(--admin-text);
    font: inherit;
    font-size: 13px;
    outline: none;
    transition:
      border-color 0.12s ease,
      box-shadow 0.12s ease;
  }

  .admin-combobox :global(.admin-combobox-input:focus) {
    border-color: var(--admin-ring);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent);
  }

  .admin-combobox :global(.admin-combobox-trigger) {
    position: absolute;
    inset: 0 0 0 auto;
    display: grid;
    width: var(--ui-control-height, 36px);
    place-items: center;
    border: 0;
    background: transparent;
    color: var(--admin-muted);
    cursor: pointer;
  }

  :global(.admin-combobox-icon-open) {
    transform: rotate(180deg);
  }

  :global(.admin-combobox-content) {
    min-width: var(--bits-combobox-anchor-width);
  }

  @media (max-width: 639px) {
    :global(.admin-combobox-content) {
      width: var(--bits-combobox-anchor-width);
    }
  }
  @media (max-width: 560px) {
    .admin-combobox :global(.admin-combobox-input[data-control-size]) {
      font-size: 16px;
    }
  }

  :global(.admin-combobox-group-label) {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0.5rem 0.625rem 0.3rem;
    color: var(--admin-muted);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  :global(.admin-combobox-group-label::after) {
    content: "";
    flex: 1 1 auto;
    height: 1px;
    background: var(--admin-border);
  }

  :global(.admin-combobox-group-label:not(:first-child)) {
    margin-top: 4px;
    border-top: 1px solid var(--admin-border);
    padding-top: 0.6rem;
  }

  :global(.admin-combobox-status) {
    padding: 10px;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.4;
  }
</style>

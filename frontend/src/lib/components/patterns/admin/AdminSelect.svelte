<script>
  import { Check, ChevronDown } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";

  export let value = "";
  export let items = [];
  export let ariaLabel = "";
  export let placeholder = "";
  export let disabled = false;
  export let side = "bottom";
  export let align = "start";
  export let sideOffset = 6;
  export let collisionPadding = 12;
  export let onValueChange = () => {};
  let className = "";
  export { className as class };

  $: selected = items.find((item) => item.value === value);

  function handleValueChange(next) {
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
        {#each items as item (item.value)}
          <Select.Item value={item.value} label={item.label} class="admin-select-item">
            <span>{item.label}</span>
            <Check size={14} class="admin-select-item-check" />
          </Select.Item>
        {/each}
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>

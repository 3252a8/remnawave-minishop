<script lang="ts">
  import { Checkbox as CheckboxPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { Check } from "./icons.js";

  type Props = CheckboxPrimitive.RootProps & {
    ariaLabel?: string;
    onCheckedChange?: (checked: boolean) => void;
  };

  let {
    checked = $bindable(false),
    disabled = false,
    indeterminate = false,
    ariaLabel = "",
    onCheckedChange = () => {},
    class: className = "",
    ...rest
  }: Props = $props();

  function handleCheckedChange(next: unknown) {
    checked = Boolean(next);
    onCheckedChange(checked);
  }
</script>

<CheckboxPrimitive.Root
  class={cn("ui-checkbox", className)}
  {checked}
  {disabled}
  {indeterminate}
  aria-label={ariaLabel}
  onCheckedChange={handleCheckedChange}
  {...rest}
>
  {#if checked || indeterminate}
    <Check size={13} strokeWidth={3} aria-hidden="true" />
  {/if}
</CheckboxPrimitive.Root>

<style>
  :global(.ui-checkbox) {
    appearance: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    padding: 0;
    border: 1px solid var(--admin-border-strong, var(--border));
    border-radius: 4px;
    background: color-mix(
      in srgb,
      var(--admin-bg, var(--panel)) 84%,
      var(--admin-surface-2, transparent)
    );
    color: #fff;
    cursor: pointer;
    outline: none;
    transition:
      background 0.14s ease,
      border-color 0.14s ease,
      box-shadow 0.14s ease;
  }

  :global(.ui-checkbox:hover) {
    border-color: var(--admin-ring, var(--accent));
  }

  :global(.ui-checkbox[data-state="checked"]),
  :global(.ui-checkbox[data-state="indeterminate"]) {
    border-color: color-mix(in srgb, var(--accent) 82%, transparent);
    background: var(--accent);
  }

  :global(.ui-checkbox:focus-visible) {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
  }

  :global(.ui-checkbox:disabled) {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>

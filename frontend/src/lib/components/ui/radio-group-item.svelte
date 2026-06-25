<script lang="ts">
  import { RadioGroup as RadioGroupPrimitive } from "bits-ui";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = Omit<RadioGroupPrimitive.ItemProps, "children"> & {
    ariaLabel?: string;
    children?: Snippet;
  };

  let {
    value = "",
    disabled = false,
    ariaLabel = "",
    class: className = "",
    children,
    ...rest
  }: Props = $props();
</script>

<RadioGroupPrimitive.Item
  class={cn("ui-radio-item", className)}
  {value}
  {disabled}
  aria-label={ariaLabel || value}
  {...rest}
>
  <span class="ui-radio-indicator" aria-hidden="true"></span>
  {@render children?.()}
</RadioGroupPrimitive.Item>

<style>
  :global(.ui-radio-item) {
    appearance: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    padding: 0;
    border: 1px solid var(--admin-border-strong, var(--border));
    border-radius: 999px;
    background: color-mix(
      in srgb,
      var(--admin-bg, var(--panel)) 84%,
      var(--admin-surface-2, transparent)
    );
    cursor: pointer;
    outline: none;
    transition:
      border-color 0.14s ease,
      box-shadow 0.14s ease;
  }

  :global(.ui-radio-item:hover) {
    border-color: var(--admin-ring, var(--accent));
  }

  :global(.ui-radio-item:focus-visible) {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
  }

  :global(.ui-radio-item:disabled) {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .ui-radio-indicator {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--accent);
    opacity: 0;
    transform: scale(0.6);
    transition:
      opacity 0.14s ease,
      transform 0.14s ease;
  }

  :global(.ui-radio-item[data-state="checked"]) {
    border-color: var(--accent);
  }

  :global(.ui-radio-item[data-state="checked"]) .ui-radio-indicator {
    opacity: 1;
    transform: scale(1);
  }
</style>

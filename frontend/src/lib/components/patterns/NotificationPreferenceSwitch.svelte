<script lang="ts">
  import { Switch } from "$components/ui/index.js";

  let {
    checked,
    disabled = false,
    ariaLabel,
    onCheckedChange,
  }: {
    checked: boolean;
    disabled?: boolean;
    ariaLabel: string;
    onCheckedChange: (checked: boolean) => void;
  } = $props();
</script>

<Switch.Root
  {checked}
  {disabled}
  aria-label={ariaLabel}
  {onCheckedChange}
  class="notification-preferences__switch"
>
  <Switch.Thumb class="notification-preferences__thumb" />
</Switch.Root>

<style>
  :global(.notification-preferences__switch) {
    position: relative;
    width: 42px;
    height: 24px;
    padding: 2px;
    border: 0;
    border-radius: 999px;
    background: var(--panel-3);
    cursor: pointer;
    transition: background 160ms ease;
  }

  :global(.notification-preferences__switch[data-state="checked"]) {
    background: var(--accent);
  }

  :global(.notification-preferences__switch:disabled) {
    cursor: wait;
    opacity: 0.58;
  }

  :global(.notification-preferences__thumb) {
    display: block;
    width: 20px;
    height: 20px;
    border-radius: 999px;
    /* White knob in both themes; a text-coloured knob turned near-black in light. */
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    transform: translateX(0);
    transition: transform 160ms ease;
  }

  :global(.notification-preferences__thumb[data-state="checked"]) {
    transform: translateX(18px);
  }

  :global(.notification-preferences__switch:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 3px;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(.notification-preferences__switch),
    :global(.notification-preferences__thumb) {
      transition: none;
    }
  }
</style>

<script lang="ts">
  import { Copy } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";

  type Props = {
    value: unknown;
    text?: string;
    copyLabel: string;
    kind?: string;
    showIcon?: boolean;
    oncopy?: (value: string) => void;
    class?: string;
  };

  let {
    value,
    text = "",
    copyLabel,
    kind = "",
    showIcon = true,
    oncopy = () => {},
    class: className = "",
  }: Props = $props();

  const copyValue = $derived(value == null ? "" : String(value));
  const displayText = $derived(text || copyValue);

  function handleCopy(event: MouseEvent): void {
    event.stopPropagation();
    if (copyValue) oncopy(copyValue);
  }
</script>

<button
  type="button"
  class={cn("admin-copyable-value", className)}
  data-copyable-value
  data-copy-kind={kind || undefined}
  aria-label={copyLabel}
  title={copyLabel}
  disabled={!copyValue}
  onclick={handleCopy}
>
  <span>{displayText}</span>
  {#if showIcon}<Copy size={12} aria-hidden="true" />{/if}
</button>

<style>
  .admin-copyable-value {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    max-width: 100%;
    min-width: 0;
    margin: -2px;
    padding: 2px;
    overflow: hidden;
    border: 0;
    border-radius: 5px;
    background: transparent;
    color: inherit;
    cursor: copy;
    font: inherit;
    font-weight: inherit;
    text-align: left;
  }

  .admin-copyable-value > span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    user-select: text;
    white-space: nowrap;
    -webkit-user-select: text;
  }

  .admin-copyable-value :global(svg) {
    flex: 0 0 auto;
    opacity: 0.58;
  }

  .admin-copyable-value:hover,
  .admin-copyable-value:focus-visible {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: color-mix(in srgb, var(--accent) 70%, var(--admin-text));
    outline: none;
  }

  .admin-copyable-value:hover :global(svg),
  .admin-copyable-value:focus-visible :global(svg) {
    opacity: 1;
  }

  .admin-copyable-value:disabled {
    cursor: default;
    opacity: 1;
  }
</style>

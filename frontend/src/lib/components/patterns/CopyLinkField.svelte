<script lang="ts">
  import Input from "$components/ui/input.svelte";
  import Button from "$components/ui/button.svelte";
  import AdminButton from "./admin/AdminButton.svelte";
  import { Check, Copy } from "$components/ui/icons.js";
  import { cn } from "$lib/utils.js";

  let {
    value = "",
    copyLabel,
    inputLabel,
    unavailableLabel = "",
    variant = "webapp",
    copied = false,
    oncopy = () => {},
    class: className = "",
  }: {
    value?: string;
    copyLabel: string;
    inputLabel: string;
    unavailableLabel?: string;
    variant?: "admin" | "webapp";
    copied?: boolean;
    oncopy?: (value: string) => void;
    class?: string;
  } = $props();
</script>

{#snippet content()}
  {copyLabel}{#if copied}<Check size={17} />{:else}<Copy size={17} />{/if}
{/snippet}

<div class={cn("copy-link-field", className)} data-variant={variant}>
  <Input
    readonly
    value={value || unavailableLabel}
    aria-label={inputLabel}
    onclick={(event) => event.currentTarget.select()}
  />
  {#if variant === "admin"}
    <AdminButton variant="primary" disabled={!value} onclick={() => oncopy(value)}>
      {@render content()}
    </AdminButton>
  {:else}
    <Button disabled={!value} onclick={() => oncopy(value)}>{@render content()}</Button>
  {/if}
</div>

<style>
  .copy-link-field {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: stretch;
    gap: 8px;
    min-width: 0;
    --copy-field-height: 44px;
  }
  .copy-link-field[data-variant="admin"] {
    --copy-field-height: 36px;
  }
  .copy-link-field :global(.input),
  .copy-link-field :global(.btn),
  .copy-link-field :global(.admin-btn) {
    height: var(--copy-field-height);
    min-height: var(--copy-field-height);
  }
  .copy-link-field :global(.input) {
    min-width: 0;
    width: 100%;
    font-size: 12px;
  }
  .copy-link-field :global(svg) {
    flex-shrink: 0;
  }
</style>

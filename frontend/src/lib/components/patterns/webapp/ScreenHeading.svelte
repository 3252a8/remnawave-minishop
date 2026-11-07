<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";

  // One heading treatment for every cabinet screen: a 40px icon tile, an 18px
  // title in the text colour, a muted 13px line under it and optional actions.
  let {
    title,
    subtitle = "",
    level = 1,
    icon,
    meta,
    actions,
    stackActions = false,
    class: className = "",
  }: {
    title: string;
    subtitle?: string;
    level?: 1 | 2;
    icon?: Snippet;
    meta?: Snippet;
    actions?: Snippet;
    /** On phones, move text actions to their own full-width row under the title. */
    stackActions?: boolean;
    class?: string;
  } = $props();
</script>

<div
  class={cn("screen-heading", className)}
  class:has-actions={Boolean(actions)}
  class:stack-actions={stackActions}
>
  {#if icon}
    <span class="screen-heading-icon" aria-hidden="true">{@render icon()}</span>
  {/if}
  <div class="screen-heading-copy">
    {#if level === 1}<h1>{title}</h1>{:else}<h2>{title}</h2>{/if}
    {#if meta}{@render meta()}{:else if subtitle}<p>{subtitle}</p>{/if}
  </div>
  {#if actions}
    <div class="screen-heading-actions">{@render actions()}</div>
  {/if}
</div>

<style>
  .screen-heading {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  .screen-heading.has-actions {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .screen-heading-icon {
    display: grid;
    width: 40px;
    height: 40px;
    place-items: center;
    border-radius: var(--radius-inner);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .screen-heading-icon :global(svg) {
    width: 20px;
    height: 20px;
  }

  .screen-heading-copy {
    display: grid;
    gap: 3px;
    min-width: 0;
  }

  .screen-heading-copy h1,
  .screen-heading-copy h2 {
    margin: 0;
    color: var(--text);
    font-size: 18px;
    font-weight: 700;
    line-height: 1.25;
    overflow-wrap: anywhere;
  }

  .screen-heading-copy p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.4;
  }

  .screen-heading-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  @media (max-width: 520px) {
    .screen-heading.stack-actions {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .screen-heading.stack-actions .screen-heading-actions {
      grid-column: 1 / -1;
    }

    .screen-heading.stack-actions .screen-heading-actions > :global(*) {
      flex: 1 1 auto;
    }
  }

  :global(.theme-light) .screen-heading-icon {
    color: var(--accent-readable, var(--accent));
  }
</style>

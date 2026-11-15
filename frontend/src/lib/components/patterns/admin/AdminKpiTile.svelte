<script lang="ts">
  import { cn } from "$lib/utils.js";
  import Skeleton from "$components/ui/skeleton.svelte";
  import type { Snippet } from "svelte";

  type Tone = "default" | "accent" | "success" | "warning" | "danger" | "info";
  type Props = {
    label: string;
    /** The number; pass `children` instead for a composite value (net / fees). */
    value?: unknown;
    hint?: string;
    tone?: Tone;
    wide?: boolean;
    title?: string;
    class?: string;
    /** Placeholder bars with the tile's final geometry while the data loads. */
    loading?: boolean;
    /** Width of the placeholder value bar, e.g. "58%". */
    loadingWidth?: string;
    icon?: Snippet;
    delta?: Snippet;
    children?: Snippet;
  };

  let {
    label,
    value = null,
    hint = "",
    tone = "default",
    wide = false,
    title,
    class: className = "",
    loading = false,
    loadingWidth = "52%",
    icon,
    delta,
    children,
  }: Props = $props();
</script>

<!-- One KPI tile for the whole admin: muted label → value → delta → context. -->
<div
  class={cn("admin-kpi-tile", wide && "is-wide", loading && "is-loading", className)}
  data-tone={tone}
  {title}
>
  {#if loading}
    <div class="admin-kpi-tile-label"><Skeleton variant="tiny" width="64%" height="10px" /></div>
    <div class="admin-kpi-tile-value">
      <Skeleton variant="line" width={loadingWidth} height="18px" />
    </div>
  {:else}
    <div class="admin-kpi-tile-label">
      {#if icon}<span class="admin-kpi-tile-icon" aria-hidden="true">{@render icon()}</span>{/if}
      <span>{label}</span>
    </div>
    {#if children}
      {@render children()}
    {:else}
      <div class="admin-kpi-tile-value">
        {value === null || value === undefined || value === "" ? "—" : String(value)}
      </div>
    {/if}
    {#if delta}<div class="admin-kpi-tile-delta">{@render delta()}</div>{/if}
    {#if hint}<div class="admin-kpi-tile-hint">{hint}</div>{/if}
  {/if}
</div>

<style>
  .admin-kpi-tile {
    display: grid;
    align-content: start;
    gap: 4px;
    min-width: 0;
    padding: 12px 14px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface-2);
  }

  .admin-kpi-tile.is-wide {
    grid-column: 1 / -1;
  }

  .admin-kpi-tile-label {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    color: var(--admin-muted);
    font-size: 12px;
    font-weight: 500;
    line-height: 1.3;
  }

  .admin-kpi-tile-label > span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .admin-kpi-tile-icon {
    display: inline-grid;
    flex: 0 0 auto;
    place-items: center;
    color: var(--admin-muted);
  }

  .admin-kpi-tile[data-tone="accent"] .admin-kpi-tile-icon {
    color: var(--accent);
  }

  .admin-kpi-tile[data-tone="success"] .admin-kpi-tile-icon {
    color: var(--success-text, var(--success));
  }

  .admin-kpi-tile[data-tone="warning"] .admin-kpi-tile-icon {
    color: var(--warning-text, var(--warning));
  }

  .admin-kpi-tile[data-tone="danger"] .admin-kpi-tile-icon {
    color: var(--danger-text, var(--danger));
  }

  .admin-kpi-tile[data-tone="info"] .admin-kpi-tile-icon {
    color: var(--info-text, var(--info));
  }

  .admin-kpi-tile-value {
    overflow-wrap: anywhere;
    color: var(--admin-text);
    font-size: 22px;
    font-weight: 600;
    line-height: 1.15;
    font-variant-numeric: tabular-nums;
  }

  .admin-kpi-tile.is-loading .admin-kpi-tile-label {
    min-height: calc(12px * 1.3);
  }

  .admin-kpi-tile.is-loading .admin-kpi-tile-value {
    display: flex;
    align-items: center;
    min-height: calc(22px * 1.15);
  }

  .admin-kpi-tile-delta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .admin-kpi-tile-hint {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.4;
  }
</style>

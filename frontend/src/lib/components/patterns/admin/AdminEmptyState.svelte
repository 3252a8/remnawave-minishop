<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";

  type Props = Omit<HTMLAttributes<HTMLDivElement>, "children" | "class" | "title"> & {
    children?: Snippet;
    class?: string;
    tone?: "card" | "default";
    /** Structured state: what is empty, how it fills up, and one way forward. */
    title?: string;
    description?: string;
    icon?: Snippet;
    actions?: Snippet;
  };

  let {
    tone = "default",
    class: className = "",
    children,
    title = "",
    description = "",
    icon,
    actions,
    ...restProps
  }: Props = $props();
</script>

{#if title}
  <div class={cn("admin-empty", tone === "card" && "admin-empty-card", className)} {...restProps}>
    {#if icon}<span class="admin-empty-icon" aria-hidden="true">{@render icon()}</span>{/if}
    <strong>{title}</strong>
    {#if description}<p>{description}</p>{/if}
    {@render children?.()}
    {#if actions}<div class="admin-empty-actions">{@render actions()}</div>{/if}
  </div>
{:else}
  <div class={cn(tone === "card" ? "admin-card-body" : "admin-empty", className)} {...restProps}>
    {@render children?.()}
  </div>
{/if}

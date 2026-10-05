<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";
  import type { AdminBadgeVariant } from "./types";

  type Props = Omit<HTMLAttributes<HTMLSpanElement>, "children" | "class"> & {
    children?: Snippet;
    class?: string;
    variant?: AdminBadgeVariant;
    wrap?: boolean;
  };

  let {
    variant = "muted",
    wrap = false,
    class: className = "",
    children,
    ...restProps
  }: Props = $props();
</script>

<span
  class={cn(
    "admin-badge",
    wrap && "admin-badge-wrap",
    variant === "success" && "admin-badge-success",
    variant === "danger" && "admin-badge-danger",
    variant === "warning" && "admin-badge-warning",
    variant === "muted" && "admin-badge-muted",
    className
  )}
  {...restProps}
>
  {@render children?.()}
</span>

<style>
  .admin-badge-wrap {
    min-width: 0;
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
</style>

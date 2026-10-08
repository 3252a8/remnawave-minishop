<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";

  type BadgeVariant = "default" | "destructive" | "muted" | "outline" | "success";
  type Props = Omit<HTMLAttributes<HTMLSpanElement>, "class" | "children"> & {
    children?: Snippet;
    class?: string;
    variant?: BadgeVariant;
    wrap?: boolean;
  };

  let {
    variant = "default",
    wrap = false,
    class: className = "",
    children,
    ...rest
  }: Props = $props();
</script>

<span
  data-slot="badge"
  class={cn(
    "admin-cn-badge",
    wrap && "admin-cn-badge-wrap",
    variant === "outline" && "admin-cn-badge-outline",
    variant === "destructive" && "admin-cn-badge-destructive",
    variant === "success" && "admin-cn-badge-success",
    variant === "muted" && "admin-cn-badge-muted",
    className
  )}
  {...rest}
>
  {@render children?.()}
</span>

<style>
  .admin-cn-badge-wrap {
    min-width: 0;
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
</style>

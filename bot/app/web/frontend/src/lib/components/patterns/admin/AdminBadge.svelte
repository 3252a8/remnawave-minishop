<script>
  import { cn } from "$lib/utils.js";

  export let variant = "muted";
  let className = "";
  export { className as class };
</script>

<span
  class={cn(
    "admin-badge",
    variant === "success" && "admin-badge-success",
    variant === "danger" && "admin-badge-danger",
    variant === "warning" && "admin-badge-warning",
    variant === "muted" && "admin-badge-muted",
    className,
  )}
  {...$$restProps}
>
  <slot />
</span>

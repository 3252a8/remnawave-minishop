<script>
  import { cn } from "$lib/utils.js";

  let { size = "default", label = "", class: className = "", ...rest } = $props();
</script>

<span
  class={cn(
    "ui-spinner",
    size === "sm" && "ui-spinner-sm",
    size === "lg" && "ui-spinner-lg",
    className
  )}
  role={label ? "status" : undefined}
  aria-label={label || undefined}
  aria-hidden={label ? undefined : "true"}
  {...rest}
></span>

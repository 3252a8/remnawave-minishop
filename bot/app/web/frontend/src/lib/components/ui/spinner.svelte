<script>
  import { cn } from "$lib/utils.js";

  export let size = "default";
  export let label = "";
  let className = "";
  export { className as class };
</script>

<span
  class={cn("ui-spinner", size === "sm" && "ui-spinner-sm", size === "lg" && "ui-spinner-lg", className)}
  role={label ? "status" : undefined}
  aria-label={label || undefined}
  aria-hidden={label ? undefined : "true"}
  {...$$restProps}
></span>

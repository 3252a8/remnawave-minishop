<script>
  import { cn } from "$lib/utils.js";

  let { variant = "block", width = "", height = "", class: className = "", ...rest } = $props();
</script>

<span
  class={cn(
    "ui-skeleton",
    variant === "line" && "ui-skeleton-line",
    variant === "title" && "ui-skeleton-line ui-skeleton-title",
    variant === "short" && "ui-skeleton-line ui-skeleton-short",
    variant === "tiny" && "ui-skeleton-line ui-skeleton-tiny",
    variant === "badge" && "ui-skeleton-badge",
    variant === "dot" && "ui-skeleton-dot",
    className
  )}
  style={`${width ? `width:${width};` : ""}${height ? `height:${height};` : ""}`}
  aria-hidden="true"
  {...rest}
></span>

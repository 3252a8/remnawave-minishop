<script>
  import { cn } from "$lib/utils.js";

  let { error = false, class: className = "", children, ...rest } = $props();
</script>

<p class={cn("status-line", error && "error", className)} {...rest}>
  {@render children?.()}
</p>

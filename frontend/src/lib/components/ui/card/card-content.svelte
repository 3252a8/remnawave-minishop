<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card-content" class={cn("admin-cn-card-content", className)} {...rest}>
  {@render children?.()}
</div>

<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card-title" class={cn("admin-cn-card-title", className)} {...rest}>
  {@render children?.()}
</div>

<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card-header" class={cn("admin-cn-card-header", className)} {...rest}>
  {@render children?.()}
</div>

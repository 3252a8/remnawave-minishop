<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card-footer" class={cn("admin-cn-card-footer", className)} {...rest}>
  {@render children?.()}
</div>

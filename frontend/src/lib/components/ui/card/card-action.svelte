<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card-action" class={cn("admin-cn-card-action", className)} {...rest}>
  {@render children?.()}
</div>

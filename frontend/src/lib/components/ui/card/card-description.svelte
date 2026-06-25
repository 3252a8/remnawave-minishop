<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<p data-slot="card-description" class={cn("admin-cn-card-description", className)} {...rest}>
  {@render children?.()}
</p>

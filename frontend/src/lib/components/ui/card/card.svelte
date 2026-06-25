<script>
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<div data-slot="card" class={cn("admin-cn-card", className)} {...rest}>
  {@render children?.()}
</div>

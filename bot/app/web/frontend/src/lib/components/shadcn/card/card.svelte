<script>
  import { cn } from "../../../utils.js";

  let className = "";
  export { className as class };
</script>

<div data-slot="card" class={cn("admin-cn-card", className)} {...$$restProps}>
  <slot />
</div>

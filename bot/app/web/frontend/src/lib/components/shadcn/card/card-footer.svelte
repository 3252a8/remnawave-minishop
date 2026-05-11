<script>
  import { cn } from "../../../utils.js";

  let className = "";
  export { className as class };
</script>

<div data-slot="card-footer" class={cn("admin-cn-card-footer", className)} {...$$restProps}>
  <slot />
</div>

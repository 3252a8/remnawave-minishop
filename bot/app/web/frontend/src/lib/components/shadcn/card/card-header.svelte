<script>
  import { cn } from "../../../utils.js";

  let className = "";
  export { className as class };
</script>

<div data-slot="card-header" class={cn("admin-cn-card-header", className)} {...$$restProps}>
  <slot />
</div>

<script>
  import { cn } from "../../../utils.js";

  let className = "";
  export { className as class };
</script>

<p data-slot="card-description" class={cn("admin-cn-card-description", className)} {...$$restProps}>
  <slot />
</p>

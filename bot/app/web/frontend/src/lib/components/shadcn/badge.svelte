<script>
  import { cn } from "../../utils.js";

  /** @type {'default' | 'outline' | 'destructive'} */
  export let variant = "default";

  let className = "";
  export { className as class };
</script>

<span
  data-slot="badge"
  class={cn(
    "admin-cn-badge",
    variant === "outline" && "admin-cn-badge-outline",
    variant === "destructive" && "admin-cn-badge-destructive",
    className,
  )}
  {...$$restProps}
>
  <slot />
</span>

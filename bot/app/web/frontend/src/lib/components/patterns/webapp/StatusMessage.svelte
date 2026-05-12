<script>
  import { cn } from "$lib/utils.js";

  export let error = false;
  let className = "";
  export { className as class };
</script>

<p class={cn("status-line", error && "error", className)} {...$$restProps}>
  <slot />
</p>

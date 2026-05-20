<script>
  import { cn } from "$lib/utils.js";

  export let position = "absolute";
  let className = "";
  export { className as class };
</script>

<span
  data-slot="attention-dot"
  aria-hidden="true"
  class={cn("attention-dot", position === "inline" && "attention-dot-inline", className)}
  {...$$restProps}
></span>

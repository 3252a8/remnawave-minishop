<script>
  import { cn } from "$lib/utils.js";

  let { position = "absolute", class: className = "", ...rest } = $props();
</script>

<span
  data-slot="attention-dot"
  aria-hidden="true"
  class={cn("attention-dot", position === "inline" && "attention-dot-inline", className)}
  {...rest}
></span>

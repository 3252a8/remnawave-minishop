<script>
  import { cn } from "$lib/utils.js";

  let { active = false, compact = false, class: className = "", children } = $props();
</script>

<section class={cn("card", active && "card-active", compact && "card-compact", className)}>
  {@render children?.()}
</section>

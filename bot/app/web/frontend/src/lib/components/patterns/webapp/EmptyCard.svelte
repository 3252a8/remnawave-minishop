<script>
  import Card from "$components/ui/card.svelte";
  import { cn } from "$lib/utils.js";

  let className = "";
  export { className as class };
</script>

<Card class={cn("empty-card", className)} {...$$restProps}>
  <slot />
</Card>

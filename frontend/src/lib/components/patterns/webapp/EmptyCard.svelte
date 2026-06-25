<script>
  import Card from "$components/ui/card.svelte";
  import { cn } from "$lib/utils.js";

  let { class: className = "", children, ...rest } = $props();
</script>

<Card class={cn("empty-card", className)} {...rest}>
  {@render children?.()}
</Card>

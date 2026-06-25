<script>
  import { cn } from "$lib/utils.js";

  /**
   * @type {{
   *   variant?: 'default' | 'outline' | 'destructive' | 'success' | 'muted';
   *   class?: string;
   *   children?: import('svelte').Snippet;
   * }}
   */
  let { variant = "default", class: className = "", children, ...rest } = $props();
</script>

<span
  data-slot="badge"
  class={cn(
    "admin-cn-badge",
    variant === "outline" && "admin-cn-badge-outline",
    variant === "destructive" && "admin-cn-badge-destructive",
    variant === "success" && "admin-cn-badge-success",
    variant === "muted" && "admin-cn-badge-muted",
    className
  )}
  {...rest}
>
  {@render children?.()}
</span>

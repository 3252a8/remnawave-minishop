<script>
  import { cn } from "$lib/utils.js";

  export let skeleton = false;
  let className = "";
  export { className as class };
</script>

<div class="admin-table-wrap">
  <table class={cn("admin-table", skeleton && "admin-table-skeleton", className)} aria-hidden={skeleton ? "true" : undefined} {...$$restProps}>
    <slot />
  </table>
</div>

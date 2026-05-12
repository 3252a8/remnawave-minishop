<script>
  import { cn } from "$lib/utils.js";

  export let value = 0;
  export let label = "";
  let className = "";
  export { className as class };

  $: clamped = Math.max(0, Math.min(100, Number(value) || 0));
</script>

<div
  class={cn("progress", className)}
  role={label ? "progressbar" : undefined}
  aria-label={label || undefined}
  aria-valuemin={label ? "0" : undefined}
  aria-valuemax={label ? "100" : undefined}
  aria-valuenow={label ? Math.round(clamped) : undefined}
  {...$$restProps}
>
  <span style={`width: ${clamped}%`}></span>
</div>

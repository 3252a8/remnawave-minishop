<script>
  import { cn } from "$lib/utils.js";

  export let title = "";
  export let value = "";
  export let left = "";
  export let percent = 0;
  export let warning = false;
  export let premium = false;
  export let label = "";

  $: clamped = Math.max(0, Math.min(100, Number(percent) || 0));
</script>

<div class={cn("admin-traffic-card", warning && "admin-traffic-card-warning", premium && "admin-traffic-card-premium")}>
  <div class="admin-traffic-head">
    <span>{title}</span>
    <strong>{value}</strong>
  </div>
  <div
    class={cn("admin-traffic-bar", premium && "admin-traffic-bar-premium")}
    aria-label={label || title}
    role="progressbar"
    aria-valuemin="0"
    aria-valuemax="100"
    aria-valuenow={Math.round(clamped)}
  >
    <span style={`width: ${clamped}%`}></span>
  </div>
  <div class="admin-traffic-meta">
    <span>{left}</span>
    <span>{clamped}%</span>
  </div>
</div>

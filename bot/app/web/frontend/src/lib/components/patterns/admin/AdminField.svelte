<script>
  import { Label } from "$components/ui/primitives.js";

  export let label = "";
  export let hint = "";
</script>

<Label.Root class="admin-field-label">
  {#if label}
    <span>{label}</span>
  {/if}
  {#if hint}
    <small>{hint}</small>
  {/if}
  <slot />
</Label.Root>

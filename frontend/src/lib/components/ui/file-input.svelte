<script lang="ts">
  import { cn } from "$lib/utils.js";

  export let element: HTMLInputElement | null = null;
  export let accept: string | undefined = undefined;
  export let disabled = false;
  let className = "";
  export { className as class };
</script>

<input
  bind:this={element}
  class={cn("ui-file-input", className)}
  type="file"
  {accept}
  {disabled}
  on:change
  {...$$restProps}
/>

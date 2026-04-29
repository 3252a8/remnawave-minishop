<script>
  import { X } from "lucide-svelte";
  import { cn } from "../../utils.js";
  import Button from "./button.svelte";

  export let open = false;
  export let title = "";
  export let description = "";
  export let onclose = () => {};
  let className = "";
  export { className as class };
</script>

{#if open}
  <div class="dialog" role="dialog" aria-modal="true" aria-label={title}>
    <button class="dialog-backdrop" type="button" aria-label="Закрыть" on:click={onclose}></button>
    <section class={cn("dialog-card", className)}>
      <div class="dialog-head">
        <div>
          {#if title}<h2>{title}</h2>{/if}
          {#if description}<p>{description}</p>{/if}
        </div>
        <Button variant="icon" size="icon" onclick={onclose} aria-label="Закрыть">
          <X size={18} />
        </Button>
      </div>
      <slot />
    </section>
  </div>
{/if}

<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { HTMLInputAttributes } from "svelte/elements";

  export let value: string | number = "";
  export let type = "text";
  export let placeholder = "";
  export let inputmode: string | null | undefined = undefined;
  export let maxlength: HTMLInputAttributes["maxlength"] = undefined;
  export let autocomplete: HTMLInputAttributes["autocomplete"] = undefined;
  export let disabled = false;
  let className = "";
  export { className as class };

  $: inputmodeAttr = inputmode as HTMLInputAttributes["inputmode"];
</script>

<input
  bind:value
  class={cn("input", className)}
  on:keydown
  on:input
  on:focus
  on:blur
  {type}
  {placeholder}
  inputmode={inputmodeAttr}
  {maxlength}
  {autocomplete}
  {disabled}
  {...$$restProps}
/>

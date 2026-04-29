<script>
  import { cn } from "../../utils.js";

  export let value = "";
  export let type = "text";
  export let placeholder = "";
  export let inputmode = undefined;
  export let maxlength = undefined;
  export let autocomplete = undefined;
  export let disabled = false;
  let className = "";
  export { className as class };
</script>

<input
  bind:value
  class={cn("input", className)}
  {type}
  {placeholder}
  {inputmode}
  {maxlength}
  {autocomplete}
  {disabled}
/>

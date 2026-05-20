<script>
  export let value = "";
  export let rows = 3;
  export let disabled = false;
  export let placeholder = "";
  export let maxlength = undefined;
  export let ariaLabel = "";
  let className = "";
  export { className as class };
</script>

<textarea
  class={`textarea ${className}`.trim()}
  bind:value
  {rows}
  {disabled}
  {placeholder}
  {maxlength}
  aria-label={ariaLabel || placeholder}
  on:input
  on:keydown
  {...$$restProps}
></textarea>

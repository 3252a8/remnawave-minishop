<script>
  export let maxHeight = "100%";
  export let element = null;
  let className = "";
  export { className as class };
</script>

<div
  bind:this={element}
  class={`scroll-area ${className}`.trim()}
  style={`max-height:${maxHeight};`}
  {...$$restProps}
>
  <slot />
</div>

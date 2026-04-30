<script>
  export let number = "";
  export let label = "";
  export let wide = false;
</script>

<section class:wide class="preview-phone-wrap">
  <h2><span>{number}.</span> {label}</h2>
  <div class="preview-phone">
    <slot />
  </div>
</section>

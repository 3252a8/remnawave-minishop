<script>
  let { number = "", label = "", wide = false, children } = $props();
</script>

<section class:wide class="preview-phone-wrap">
  <h2><span>{number}.</span> {label}</h2>
  <div class="preview-phone">
    {@render children?.()}
  </div>
</section>

<script>
  import { ArrowLeft } from "$components/ui/icons.js";

  export let title = "";
  export let subtitle = "";
</script>

<header class="screen-head">
  <button class="btn btn-icon btn-square" type="button" aria-label="Назад">
    <ArrowLeft size={18} />
  </button>
  <div class="center-copy">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <span></span>
</header>

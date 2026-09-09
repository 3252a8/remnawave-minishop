<script lang="ts">
  import { ArrowLeft } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";

  type Props = {
    title?: string;
    subtitle?: string;
  };

  let { title = "", subtitle = "" }: Props = $props();
</script>

<header class="screen-head">
  <Button variant="icon" size="icon" aria-label="Назад">
    <ArrowLeft size={18} />
  </Button>
  <div class="center-copy">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <span></span>
</header>

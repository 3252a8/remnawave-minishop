<script lang="ts">
  import type { ThemeEffectTarget } from "$lib/webapp/themeEffectsSdk";
  let { name }: { name: ThemeEffectTarget } = $props();
</script>

<div class="theme-effect-surface" data-theme-effect-target={name} aria-hidden="true"></div>

<style>
  .theme-effect-surface {
    position: absolute;
    inset: 0;
    overflow: hidden;
    border-radius: inherit;
    pointer-events: none;
    z-index: -1;
  }
</style>

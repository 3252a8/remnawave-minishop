<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    wrapper = $bindable(),
    children,
  }: {
    wrapper?: HTMLElement;
    isOpen: boolean;
    isDialog: boolean;
    children: Snippet;
  } = $props();
</script>

<div bind:this={wrapper}>
  {@render children()}
</div>

<style>
  div {
    display: flex;
    flex-direction: column;
  }
</style>

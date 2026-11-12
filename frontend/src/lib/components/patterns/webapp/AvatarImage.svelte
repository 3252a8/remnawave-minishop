<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    src,
    fallbackSrc = "",
    alt = "",
    placeholder,
  }: { src: string; fallbackSrc?: string; alt?: string; placeholder: Snippet } = $props();

  const sources = $derived([...new Set([src, fallbackSrc].filter(Boolean))]);
  let attempt = $state.raw<{ sources: string[]; index: number }>();
  const index = $derived(attempt?.sources === sources ? attempt.index : 0);
  const imageUrl = $derived(sources[index]);
</script>

{#if imageUrl}
  {#key imageUrl}
    <img
      src={imageUrl}
      {alt}
      loading="lazy"
      referrerpolicy="no-referrer"
      onerror={() => (attempt = { sources, index: index + 1 })}
    />
  {/key}
{:else}
  {@render placeholder()}
{/if}

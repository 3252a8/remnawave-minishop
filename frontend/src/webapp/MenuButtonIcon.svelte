<script lang="ts">
  import type { Component } from "svelte";
  import * as Icons from "$components/ui/icons.js";

  type IconComponent = Component<{ size?: number | string }>;
  const iconRegistry: Record<string, unknown> = Icons;

  let { icon = "" }: { icon?: string } = $props();
  const Icon = $derived(
    typeof iconRegistry[icon] === "function" ? (iconRegistry[icon] as IconComponent) : null
  );
</script>

{#if Icon}<Icon size={21} />{/if}

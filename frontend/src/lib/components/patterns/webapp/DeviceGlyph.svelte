<script lang="ts">
  import { Laptop, Monitor, Smartphone, Tablet, Tv } from "$components/ui/icons.js";
  import { resolveDeviceShape } from "$lib/webapp/deviceGlyph.js";

  type Props = {
    device?: unknown;
    size?: number;
  };

  let { device = null, size = 24 }: Props = $props();

  const shape = $derived(resolveDeviceShape(device as Record<string, unknown> | null));
</script>

{#if shape === "tablet"}
  <Tablet class="device-glyph" data-device-shape={shape} {size} aria-hidden="true" />
{:else if shape === "laptop"}
  <Laptop class="device-glyph" data-device-shape={shape} {size} aria-hidden="true" />
{:else if shape === "desktop"}
  <Monitor class="device-glyph" data-device-shape={shape} {size} aria-hidden="true" />
{:else if shape === "tv"}
  <Tv class="device-glyph" data-device-shape={shape} {size} aria-hidden="true" />
{:else}
  <Smartphone class="device-glyph" data-device-shape={shape} {size} aria-hidden="true" />
{/if}

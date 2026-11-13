<script lang="ts">
  import { ImageViewer } from "$components/ui/index.js";

  type ImageViewerLabels = {
    open: string;
    title: string;
    close: string;
    zoomIn: string;
    zoomOut: string;
    reset: string;
  };

  let {
    imageUrl,
    loadImage,
    imageViewerLabels,
    t,
  }: {
    imageUrl: string;
    loadImage?: (url: string) => Promise<Blob>;
    imageViewerLabels: ImageViewerLabels;
    t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  } = $props();

  let resolvedImageUrl = $state("");
  let imageLoadFailed = $state(false);
  let imageViewerOpen = $state(false);

  $effect(() => {
    const source = imageUrl;
    const loader = loadImage;
    resolvedImageUrl = "";
    imageLoadFailed = false;
    imageViewerOpen = false;
    if (!source) return;
    if (!loader) {
      resolvedImageUrl = source;
      return;
    }

    let active = true;
    let objectUrl = "";
    void loader(source)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        resolvedImageUrl = objectUrl;
      })
      .catch(() => {
        if (active) imageLoadFailed = true;
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  });
</script>

{#if resolvedImageUrl}
  <button
    class="ticket-message-image-trigger"
    type="button"
    aria-label={imageViewerLabels.open}
    onclick={() => (imageViewerOpen = true)}
  >
    <img
      class="ticket-message-image"
      src={resolvedImageUrl}
      alt={t("wa_message_image_alt", {}, "Attached image")}
      loading="lazy"
    />
  </button>
{:else if imageLoadFailed}
  <span class="ticket-message-image-error" role="alert">
    {t("wa_message_image_load_failed", {}, "The attached image could not be loaded")}
  </span>
{/if}

<ImageViewer
  open={imageViewerOpen}
  src={resolvedImageUrl}
  alt={t("wa_message_image_alt", {}, "Attached image")}
  title={imageViewerLabels.title}
  closeLabel={imageViewerLabels.close}
  zoomInLabel={imageViewerLabels.zoomIn}
  zoomOutLabel={imageViewerLabels.zoomOut}
  resetLabel={imageViewerLabels.reset}
  onclose={() => (imageViewerOpen = false)}
/>

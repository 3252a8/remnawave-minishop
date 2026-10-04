const failedPreviews = new WeakSet<Blob>();

/** Image decode/src failures invalidate every cache entry holding the same Blob. */
export function rejectEmojiPreviewBlob(blob: Blob): void {
  failedPreviews.add(blob);
}

/** Only bounded raster previews may enter image presentation or the Blob cache. */
export function isEmojiPreviewBlob(blob: Blob): boolean {
  return (
    !failedPreviews.has(blob) &&
    /^image\/(png|webp|jpeg|gif)$/i.test(blob.type) &&
    blob.size > 0 &&
    blob.size <= 2 * 1024 * 1024
  );
}

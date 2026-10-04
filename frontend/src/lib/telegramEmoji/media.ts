const failedPreviews = new WeakSet<Blob>();
const invalidations = new WeakMap<Blob, Set<() => void>>();

export function onEmojiPreviewRejected(blob: Blob, invalidate: () => void): void {
  const callbacks = invalidations.get(blob) ?? new Set();
  callbacks.add(invalidate);
  invalidations.set(blob, callbacks);
}

/** Image decode/src failures invalidate every cache entry holding the same Blob. */
export function rejectEmojiPreviewBlob(blob: Blob): void {
  failedPreviews.add(blob);
  for (const invalidate of invalidations.get(blob) ?? []) invalidate();
  invalidations.delete(blob);
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

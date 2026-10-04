const PREVIEW_STATE = Symbol.for("minishop.emojiPreviewState.v1");
type PreviewState = { rejected: boolean; invalidations: Set<() => void> };
function previewState(blob: Blob): PreviewState {
  const existing = Reflect.get(blob, PREVIEW_STATE) as PreviewState | undefined;
  if (existing) return existing;
  const state: PreviewState = { rejected: false, invalidations: new Set() };
  // The API and image renderer may come from separately built app/admin bundles.
  Object.defineProperty(blob, PREVIEW_STATE, { value: state });
  return state;
}

export function onEmojiPreviewRejected(blob: Blob, invalidate: () => void): void {
  const state = previewState(blob);
  if (state.rejected) invalidate();
  else state.invalidations.add(invalidate);
}

/** Image decode/src failures invalidate every cache entry holding the same Blob. */
export function rejectEmojiPreviewBlob(blob: Blob): void {
  const state = previewState(blob);
  state.rejected = true;
  const callbacks = [...state.invalidations];
  state.invalidations.clear();
  for (const invalidate of callbacks) invalidate();
}

/** Only bounded raster previews may enter image presentation or the Blob cache. */
export function isEmojiPreviewBlob(blob: Blob): boolean {
  return (
    !(Reflect.get(blob, PREVIEW_STATE) as PreviewState | undefined)?.rejected &&
    /^image\/(png|webp|jpeg|gif)$/i.test(blob.type) &&
    blob.size > 0 &&
    blob.size <= 2 * 1024 * 1024
  );
}

/** The keyboard may resize or pan the visible area without resizing the page. */
export function observeVisualViewport(
  update: (viewport: { height: number; top: number }) => void
): () => void {
  const viewport = window.visualViewport;
  const sync = () =>
    update({ height: viewport?.height ?? window.innerHeight, top: viewport?.offsetTop ?? 0 });
  sync();
  viewport?.addEventListener("resize", sync);
  viewport?.addEventListener("scroll", sync);
  window.addEventListener("resize", sync);
  return () => {
    viewport?.removeEventListener("resize", sync);
    viewport?.removeEventListener("scroll", sync);
    window.removeEventListener("resize", sync);
  };
}

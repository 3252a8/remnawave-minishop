/** Follow incoming messages and viewport changes while the reader is near the latest reply. */
export function followTicketMessages(viewport: HTMLElement): () => void {
  let atBottom = true;
  viewport.scrollTop = viewport.scrollHeight;
  const trackPosition = () => {
    atBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 64;
  };
  const observer = new ResizeObserver(() => {
    if (atBottom) viewport.scrollTop = viewport.scrollHeight;
  });
  observer.observe(viewport);
  if (viewport.firstElementChild) observer.observe(viewport.firstElementChild);
  viewport.addEventListener("scroll", trackPosition, { passive: true });
  return () => {
    observer.disconnect();
    viewport.removeEventListener("scroll", trackPosition);
  };
}

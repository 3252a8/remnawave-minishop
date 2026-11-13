/** Keep a direct link aligned while asynchronously loaded cards change the layout. */
export function trackLinkedSubsection(
  content: HTMLElement,
  hasTarget: () => boolean,
  getTarget: () => Element | null
) {
  let frame = 0;
  let previousTop: number | undefined;
  const resize = new ResizeObserver(queueScroll);
  const mutations = new MutationObserver(queueScroll);
  const interactionEvents = ["wheel", "touchstart", "pointerdown", "keydown"] as const;

  function queueScroll() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const target = getTarget();
      if (!target) return;
      const top = target.getBoundingClientRect().top;
      if (previousTop !== undefined && Math.abs(top - previousTop) < 1) return;
      target.scrollIntoView({ block: "start", behavior: "instant" });
      previousTop = target.getBoundingClientRect().top;
    });
  }

  function stopTracking() {
    cancelAnimationFrame(frame);
    resize.disconnect();
    mutations.disconnect();
    for (const event of interactionEvents) window.removeEventListener(event, stopTracking);
  }

  function track() {
    stopTracking();
    if (!hasTarget()) return;
    previousTop = undefined;
    resize.observe(content);
    mutations.observe(content, { childList: true, subtree: true });
    for (const event of interactionEvents)
      window.addEventListener(event, stopTracking, { passive: true });
    queueScroll();
  }

  track();
  window.addEventListener("popstate", track);
  return () => {
    stopTracking();
    window.removeEventListener("popstate", track);
  };
}

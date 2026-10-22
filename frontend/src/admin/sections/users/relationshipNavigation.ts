import type { Core, EventObject } from "cytoscape";

type Sample = { time: number; x: number; y: number };

/** Extend native gestures while retaining Cytoscape's hit testing and pinch zoom. */
export function enhanceRelationshipNavigation(graph: Core): () => void {
  const container = graph.container();
  const owner = container?.ownerDocument.defaultView;
  if (!container || !owner) return () => {};
  const document = container.ownerDocument;
  const reducedMotion = owner.matchMedia("(prefers-reduced-motion: reduce)");
  const gain = 1.5;
  const friction = 180;
  let current = { ...graph.pan() };
  let before = current;
  let samples: Sample[] = [];
  let dragging = false;
  let frame = 0;
  let coasting = false;
  let wheelStartZoom = graph.zoom();

  function stop(): void {
    owner!.cancelAnimationFrame(frame);
    frame = 0;
  }

  function cancelGesture(): void {
    stop();
    dragging = false;
    samples = [];
  }

  function sample(): Sample {
    return { time: owner!.performance.now(), ...graph.pan() };
  }

  function begin(event: EventObject): void {
    cancelGesture();
    if (event.originalEvent?.button != null && event.originalEvent.button !== 0) return;
    dragging = true;
    samples = [sample()];
  }

  function capture(): void {
    // Any programmatic pan takes ownership immediately; our own frames do not.
    if (!coasting) stop();
    before = current;
    current = { ...graph.pan() };
  }

  function accelerate(): void {
    const x = (current.x - before.x) * (gain - 1);
    const y = (current.y - before.y) * (gain - 1);
    // Native dragpan follows panBy and precedes pointer re-projection. This
    // correction emits pan/viewport, never dragpan, so it cannot recurse.
    if (x || y) graph.panBy({ x, y });
    if (!dragging) return;
    const next = sample();
    samples.push(next);
    while (samples.length > 2 && samples[0].time < next.time - 80) samples.shift();
  }

  function release(): void {
    const first = samples[0];
    const last = samples.at(-1);
    dragging = false;
    samples = [];
    if (!first || !last || reducedMotion.matches || document.hidden) return;
    const started = owner!.performance.now();
    const duration = last.time - first.time;
    // A held release or a tap must not turn into a flick.
    if (started - last.time > 80 || duration < 16) return;
    let vx = (last.x - first.x) / duration;
    let vy = (last.y - first.y) / duration;
    const speed = Math.hypot(vx, vy);
    if (speed < 0.08) return;
    const limit = Math.min(1, 2 / speed);
    vx *= limit;
    vy *= limit;
    let previousDecay = 1;
    const coast = (now: number) => {
      frame = 0;
      if (graph.destroyed() || document.hidden || reducedMotion.matches) return;
      const elapsed = now - started;
      const decay = Math.exp(-elapsed / friction);
      // Integrate decay over real time so 60/120 Hz displays travel equally far.
      const distance = friction * (previousDecay - decay);
      previousDecay = decay;
      coasting = true;
      graph.panBy({ x: vx * distance, y: vy * distance });
      coasting = false;
      if (elapsed < 800 && Math.hypot(vx, vy) * decay > 0.02)
        frame = owner!.requestAnimationFrame(coast);
    };
    frame = owner!.requestAnimationFrame(coast);
  }

  function touchStart(event: TouchEvent): void {
    if (event.touches.length > 1) cancelGesture();
  }

  function wheelStart(event: WheelEvent): void {
    if (!container!.contains(event.target as Node)) return;
    cancelGesture();
    wheelStartZoom = graph.zoom();
  }

  function speedUpWheel(event: EventObject): void {
    if (event.originalEvent?.type !== "wheel") return;
    const wheel = event.originalEvent as WheelEvent;
    // Trackpad pinch (Ctrl+wheel) keeps its native scale. Fine scrolling gets
    // a smaller boost than coarse wheel notches, with a bounded step for both.
    if (wheel.ctrlKey) return;
    const coarse = wheel.deltaMode !== 0 || Math.abs(wheel.deltaY) >= 40;
    const delta = Math.log(graph.zoom() / wheelStartZoom) * (coarse ? 5 : 1.8);
    const step = Math.max(-Math.log(1.25), Math.min(Math.log(1.25), delta));
    const level = Math.max(
      graph.minZoom(),
      Math.min(graph.maxZoom(), wheelStartZoom * Math.exp(step))
    );
    graph.zoom({ level, position: event.position });
  }

  function visibility(): void {
    if (document.hidden) cancelGesture();
  }

  graph.on("pan", capture);
  graph.on("dragpan", accelerate);
  graph.on("tapstart", begin);
  graph.on("tapend", release);
  graph.on("zoom resize cxttapstart", cancelGesture);
  graph.on("select", stop);
  graph.on("scrollzoom", speedUpWheel);
  graph.on("destroy", destroy);
  container.addEventListener("touchstart", touchStart, { passive: true });
  container.addEventListener("touchcancel", cancelGesture);
  // Observe before the native container listener, without replacing its wheel
  // normalization, ancestor-scroll guard, or prevention of zoom during a drag.
  owner.addEventListener("wheel", wheelStart, { capture: true, passive: true });
  owner.addEventListener("pointerdown", stop, true);
  owner.addEventListener("keydown", cancelGesture);
  owner.addEventListener("popstate", cancelGesture);
  owner.addEventListener("blur", cancelGesture);
  document.addEventListener("visibilitychange", visibility);
  reducedMotion.addEventListener("change", cancelGesture);

  function destroy(): void {
    cancelGesture();
    graph.off("pan", capture);
    graph.off("dragpan", accelerate);
    graph.off("tapstart", begin);
    graph.off("tapend", release);
    graph.off("zoom resize cxttapstart", cancelGesture);
    graph.off("select", stop);
    graph.off("scrollzoom", speedUpWheel);
    graph.off("destroy", destroy);
    container!.removeEventListener("touchstart", touchStart);
    container!.removeEventListener("touchcancel", cancelGesture);
    owner!.removeEventListener("wheel", wheelStart, true);
    owner!.removeEventListener("pointerdown", stop, true);
    owner!.removeEventListener("keydown", cancelGesture);
    owner!.removeEventListener("popstate", cancelGesture);
    owner!.removeEventListener("blur", cancelGesture);
    document.removeEventListener("visibilitychange", visibility);
    reducedMotion.removeEventListener("change", cancelGesture);
  }

  return destroy;
}

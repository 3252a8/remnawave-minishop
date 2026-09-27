import type { ThemeEffectHost, ThemeEffectContext } from "../../frontend/src/lib/webapp/themeEffectsSdk";

/** Small dependency-free adapter showing pointer effects and automatic cleanup. */
export function mount(host: ThemeEffectHost, initial: ThemeEffectContext) {
  let context = initial;
  const nodes = new Map<HTMLElement, HTMLDivElement>();
  function reconcile() {
    const targets = host.targets("home.header.surface");
    for (const [target, layer] of nodes) if (!targets.includes(target)) { layer.remove(); nodes.delete(target); }
    for (const target of targets) if (!nodes.has(target)) {
      const layer = document.createElement("div");
      layer.style.cssText = "position:absolute;inset:12px;border-radius:24px;background:linear-gradient(135deg,#38bdf844,#a78bfa66);transition:transform 150ms ease-out";
      target.append(layer); nodes.set(target, layer);
    }
  }
  reconcile();
  const unwatch = host.watchTargets(reconcile);
  const unlisten = host.listen(window, "pointermove", (event) => {
    if (!(event instanceof PointerEvent) || event.pointerType !== "mouse" || context.reducedMotion) return;
    for (const [target, layer] of nodes) {
      const rect = target.getBoundingClientRect();
      const x = Math.max(-1, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width) * 2 - 1));
      const y = Math.max(-1, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height) * 2 - 1));
      layer.style.transform = `perspective(500px) rotateX(${-y * 5}deg) rotateY(${x * 5}deg)`;
    }
  });
  return {
    update(next: ThemeEffectContext) { context = next; },
    dispose() { unwatch(); unlisten(); for (const layer of nodes.values()) layer.remove(); nodes.clear(); },
  };
}

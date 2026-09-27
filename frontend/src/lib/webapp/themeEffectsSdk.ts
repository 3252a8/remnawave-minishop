/** Public API for trusted theme adapters. This is a lifecycle contract, not a sandbox. */
export type ThemeEffectTarget = "shell.background" | "home.header.surface" | "home.card.surface";
export interface ThemeEffectContext {
  variant: "light" | "dark";
  colors: Record<string, string>;
  language: string;
  reducedMotion: boolean;
}
export interface ThemeEffectInstance {
  update(context: ThemeEffectContext): void | Promise<void>;
  dispose(): void | Promise<void>;
}
export interface ThemeEffectHost {
  signal: AbortSignal;
  targets(name: ThemeEffectTarget): HTMLElement[];
  watchTargets(callback: () => void): () => void;
  asset(name: string): string;
  listen(target: EventTarget, name: string, callback: EventListener): () => void;
  animation(callback: (time: number) => void): () => void;
  timeout(callback: () => void, milliseconds: number): () => void;
  observe(target: Element, callback: ResizeObserverCallback): () => void;
}
export interface ThemeEffectModule {
  mount(
    host: ThemeEffectHost,
    context: ThemeEffectContext
  ): ThemeEffectInstance | Promise<ThemeEffectInstance>;
}

export function createThemeEffectHost(
  allowed: ThemeEffectTarget[],
  assets: Record<string, string>
) {
  const controller = new AbortController();
  const cleanups = new Set<() => void>();
  function register(cleanup: () => void) {
    let active = true;
    const cancel = () => {
      if (!active) return;
      active = false;
      cleanups.delete(cancel);
      cleanup();
    };
    cleanups.add(cancel);
    if (controller.signal.aborted) cancel();
    return cancel;
  }
  function targets(name: ThemeEffectTarget): HTMLElement[] {
    if (!allowed.includes(name) || controller.signal.aborted) return [];
    return Array.from(
      document.querySelectorAll<HTMLElement>(`[data-theme-effect-target="${name}"]`)
    );
  }
  const host: ThemeEffectHost = {
    signal: controller.signal,
    targets,
    asset(name) {
      if (!Object.hasOwn(assets, name)) throw new Error("undeclared_theme_asset");
      return assets[name];
    },
    watchTargets(callback) {
      let previous = allowed.flatMap(targets);
      const observer = new MutationObserver(() => {
        const next = allowed.flatMap(targets);
        if (next.length === previous.length && next.every((item, i) => item === previous[i]))
          return;
        previous = next;
        callback();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      return register(() => observer.disconnect());
    },
    listen(target, name, callback) {
      target.addEventListener(name, callback, { signal: controller.signal });
      return register(() => target.removeEventListener(name, callback));
    },
    animation(callback) {
      let cancelled = false;
      let frame = 0;
      const render = (time: number) => {
        if (cancelled || controller.signal.aborted) return;
        callback(time);
        if (!cancelled && !controller.signal.aborted) frame = requestAnimationFrame(render);
      };
      frame = requestAnimationFrame(render);
      return register(() => {
        cancelled = true;
        cancelAnimationFrame(frame);
      });
    },
    timeout(callback, milliseconds) {
      const timer = window.setTimeout(
        () => {
          cancel();
          if (!controller.signal.aborted) callback();
        },
        Math.max(0, milliseconds)
      );
      const cancel = register(() => clearTimeout(timer));
      return cancel;
    },
    observe(target, callback) {
      const observer = new ResizeObserver(callback);
      observer.observe(target);
      return register(() => observer.disconnect());
    },
  };
  return {
    host,
    dispose() {
      controller.abort();
      for (const cancel of [...cleanups]) {
        try {
          cancel();
        } catch {
          /* Continue releasing the other owned resources. */
        }
      }
    },
  };
}

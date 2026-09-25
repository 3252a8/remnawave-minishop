/**
 * A screen that is fetched the first time the customer opens it.
 *
 * The mini app boots into home and most sessions never leave it, so the code
 * behind the other tabs — the rich text editor on support most of all — has no
 * business being in the first payload. Each screen keeps its own chunk, is
 * imported on demand, and stays loaded afterwards, so switching back is
 * instant.
 *
 * The component type is inferred from the loader, so a screen rendered this way
 * type-checks its props exactly as a statically imported one does.
 */
export type LazyScreen<Component> = {
  /** The loaded component, or `null` while it is still on its way. */
  readonly component: Component | null;
  /** Whether the most recent chunk request failed. */
  readonly failed: boolean;
  load(): void;
};

export function lazyScreen<Component>(
  load: () => Promise<{ default: Component }>
): LazyScreen<Component> {
  let component = $state<Component | null>(null);
  let failed = $state(false);
  let pending = false;

  return {
    get component() {
      return component;
    },
    get failed() {
      return failed;
    },
    load() {
      if (component || pending) return;
      failed = false;
      pending = true;
      void load()
        .then((module) => {
          component = module.default;
        })
        .catch(() => {
          failed = true;
        })
        .finally(() => {
          pending = false;
        });
    },
  };
}

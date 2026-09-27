import type { components } from "$lib/api/openapi.generated";
import {
  createThemeEffectHost,
  type ThemeEffectContext,
  type ThemeEffectInstance,
  type ThemeEffectModule,
} from "./themeEffectsSdk";

export type ThemeEffectDescriptor = components["schemas"]["ThemeEffectsDescriptor"];
export const THEME_EFFECTS_STORAGE = "minishop-theme-effects-disabled";

export function themeEffectsDisabled(): boolean {
  if (new URLSearchParams(location.search).get("theme_effects") === "off") return true;
  try {
    return localStorage.getItem(THEME_EFFECTS_STORAGE) === "1";
  } catch {
    return false;
  }
}

export function validEffectDescriptor(effect: ThemeEffectDescriptor): boolean {
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(effect.key) || !/^[a-f0-9]{64}$/.test(effect.digest))
    return false;
  const prefix = `/api/theme-effects/assets/${effect.key}/${effect.digest}/`;
  return (
    effect.manifest.runtime === "trusted-dom" &&
    effect.manifest.api_version === 1 &&
    [effect.entry, ...effect.styles, ...Object.values(effect.assets)].every(
      (url) => url.startsWith(prefix) && !url.includes("..") && !/[\\?#%]/.test(url)
    )
  );
}

async function deadline<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timeout = 0;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timeout = window.setTimeout(() => reject(new Error("theme_effect_timeout")), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

export function createThemeEffectsRuntime(
  loadModule: (url: string) => Promise<unknown> = (url) => import(/* @vite-ignore */ url)
) {
  let generation = 0;
  let instance: ThemeEffectInstance | null = null;
  let scope: ReturnType<typeof createThemeEffectHost> | null = null;
  let styles: HTMLLinkElement[] = [];
  let executed = false;
  let digest = "";
  async function dispose() {
    generation++;
    const old = instance;
    instance = null;
    scope?.dispose();
    scope = null;
    for (const link of styles) link.remove();
    styles = [];
    for (const element of document.querySelectorAll<HTMLElement>("[data-theme-effect-target]"))
      element.replaceChildren();
    try {
      if (old) await deadline(Promise.resolve(old.dispose()), 1000);
    } catch {
      /* Reload also resets non-cooperating adapters. */
    }
  }
  return {
    get executed() {
      return executed;
    },
    get digest() {
      return digest;
    },
    dispose,
    async start(effect: ThemeEffectDescriptor, context: ThemeEffectContext) {
      if (!validEffectDescriptor(effect)) throw new Error("invalid_theme_effect_descriptor");
      const cleaning = dispose();
      const run = generation;
      await cleaning;
      if (run !== generation) return;
      const owned = createThemeEffectHost(effect.manifest.targets, effect.assets);
      scope = owned;
      digest = effect.digest;
      for (const href of effect.styles) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        document.head.appendChild(link);
        styles.push(link);
      }
      executed = true;
      try {
        const loaded = await deadline(loadModule(effect.entry), 3000);
        if (run !== generation) return;
        if (
          !loaded ||
          typeof loaded !== "object" ||
          !("mount" in loaded) ||
          typeof loaded.mount !== "function"
        )
          throw new Error("invalid_theme_effect_module");
        const mounting = Promise.resolve((loaded as ThemeEffectModule).mount(owned.host, context));
        void mounting
          .then(async (late) => {
            if (run !== generation) await late?.dispose?.();
          })
          .catch(() => {});
        const mounted = await deadline(mounting, 3000);
        if (run !== generation) return;
        if (
          !mounted ||
          typeof mounted.dispose !== "function" ||
          typeof mounted.update !== "function"
        )
          throw new Error("invalid_theme_effect_instance");
        instance = mounted;
      } catch (error) {
        if (run === generation) await dispose();
        throw error;
      }
    },
    async update(context: ThemeEffectContext) {
      if (instance) await deadline(Promise.resolve(instance.update(context)), 3000);
    },
  };
}

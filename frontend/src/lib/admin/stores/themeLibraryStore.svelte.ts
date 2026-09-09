import type { components } from "../../api/openapi.generated";
import {
  buildThemeImportPath,
  buildThemeInstallPath,
  buildThemeLibraryItemPath,
  buildThemeRollbackPath,
  buildThemePreviewPath,
} from "../../webapp/themeApiPaths";
import type { ApiClient } from "../../webapp/publicApi";
import { adminErrorMessage } from "../errors";

export type ThemeInstallation = components["schemas"]["ThemeInstallation"];
export type ThemeImport = components["schemas"]["ImportRecord"];
export type ThemeCandidate = components["schemas"]["Candidate"];
type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function createThemeLibraryStore(options: {
  api: ApiClient["api"];
  apiBlob?: ApiClient["apiBlob"];
  onChanged: () => Promise<void>;
  at: Translate;
  flash: (text: string) => void;
}) {
  const { api, apiBlob, onChanged, at, flash } = options;
  let installations = $state<ThemeInstallation[]>([]);
  let generation = $state(0);
  let writable = $state(true);
  let busy = $state(false);
  let error = $state("");
  let operation = $state<ThemeImport | null>(null);
  let idempotencyKey = "";
  let pollController: AbortController | null = null;

  function message(value: unknown): string {
    return adminErrorMessage(
      value,
      at,
      at("appearance_operation_failed", {}, "Theme operation failed.")
    );
  }
  async function load() {
    const result = await api("/admin/themes/library");
    if (!result?.ok) {
      error = message(result);
      return;
    }
    installations = result.installations || [];
    generation = result.generation;
    writable = result.writable;
  }
  async function refresh() {
    await onChanged();
    await load();
  }
  async function run(action: () => Promise<void>) {
    if (busy) return;
    busy = true;
    error = "";
    try {
      await action();
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) error = message(cause);
    } finally {
      busy = false;
    }
  }
  async function inspect(source: File | { url: string; ref: string; subdir: string }) {
    await run(async () => {
      operation = null;
      idempotencyKey = crypto.randomUUID();
      let body: FormData | string;
      if (source instanceof File) {
        if (!source.name.toLowerCase().endsWith(".zip")) throw { error: "zip_required" };
        if (source.size > 20 * 1024 * 1024) throw { error: "archive_too_large" };
        body = new FormData();
        body.append("file", source);
      } else {
        body = JSON.stringify({ source_type: "repository", ...source });
      }
      pollController?.abort();
      const controller = new AbortController();
      pollController = controller;
      let result = await api("/admin/themes/imports", {
        method: "POST",
        body,
        signal: controller.signal,
      });
      if (!result?.ok) throw result;
      operation = result.operation;
      const deadline = Date.now() + 120_000;
      while (operation && ["downloading", "validating"].includes(operation.state || "")) {
        await new Promise<void>((resolve, reject) => {
          const abort = () => {
            clearTimeout(timer);
            reject(new DOMException("Aborted", "AbortError"));
          };
          const timer = setTimeout(() => {
            controller.signal.removeEventListener("abort", abort);
            resolve();
          }, 1500);
          if (controller.signal.aborted) abort();
          else controller.signal.addEventListener("abort", abort, { once: true });
        });
        if (Date.now() > deadline) throw { error: "import_interrupted" };
        result = await api(buildThemeImportPath(operation.id), { signal: controller.signal });
        if (!result?.ok) throw result;
        operation = result.operation;
      }
      if (operation?.state === "failed") throw { error: operation.error };
      await load();
    });
  }
  async function cancel() {
    pollController?.abort();
    if (operation && operation.state !== "installed") {
      const result = await api(buildThemeImportPath(operation.id), { method: "DELETE" });
      if (!result?.ok) {
        error = message(result);
        return;
      }
    }
    operation = null;
    error = "";
  }
  async function install(choices: components["schemas"]["InstallChoice"][]) {
    let success = false;
    await run(async () => {
      if (!operation) return;
      const result = await api(buildThemeInstallPath(operation.id), {
        method: "POST",
        body: JSON.stringify({
          choices,
          expected_generation: generation,
          idempotency_key: idempotencyKey,
        }),
      });
      if (!result?.ok) throw result;
      operation = { ...operation, state: "installed", installed: result.keys };
      await refresh();
      flash(
        at(
          "appearance_demo_installed_notice",
          { count: result.keys?.length || 0 },
          "Themes installed: {count}."
        )
      );
      success = true;
    });
    return success;
  }
  async function mutate(key: string, action: "remove" | "rollback") {
    let success = false;
    await run(async () => {
      const result =
        action === "remove"
          ? await api(buildThemeLibraryItemPath(key), {
              method: "DELETE",
              body: JSON.stringify({ expected_generation: generation }),
            })
          : await api(buildThemeRollbackPath(key), {
              method: "POST",
              body: JSON.stringify({ expected_generation: generation }),
            });
      if (!result?.ok) throw result;
      await refresh();
      success = true;
    });
    return success;
  }
  async function exportThemes(keys: string[], includeOverrides = false, newKey?: string) {
    await run(async () => {
      if (!apiBlob) throw { error: "theme_export_unavailable" };
      const blob = await apiBlob("/admin/themes/export", {
        method: "POST",
        body: JSON.stringify({
          keys,
          include_overrides: includeOverrides,
          new_key: newKey || null,
        }),
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = newKey ? newKey + ".zip" : "minishop-themes.zip";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    });
  }
  async function preview(key: string, variant: "light" | "dark", importId?: string) {
    if (!apiBlob) throw { error: "theme_preview_unavailable" };
    const blob = await apiBlob(buildThemePreviewPath(key, variant, importId));
    return URL.createObjectURL(blob);
  }
  return {
    get installations() {
      return installations;
    },
    get generation() {
      return generation;
    },
    get writable() {
      return writable;
    },
    get busy() {
      return busy;
    },
    get error() {
      return error;
    },
    get operation() {
      return operation;
    },
    syncGeneration(value: number) {
      generation = value;
    },
    load,
    refresh,
    inspect,
    cancel,
    install,
    mutate,
    exportThemes,
    preview,
    message,
  };
}
export type ThemeLibraryStore = ReturnType<typeof createThemeLibraryStore>;

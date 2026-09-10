/** The documentation demo keeps packages in memory and never downloads Git repositories. */
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import type { ThemeEntry } from "../../admin/appearanceOptions";
import type { components } from "../../api/openapi.generated";
import { DEV_MOCK } from "../previewMock";
import type { PreviewThemesCatalog } from "../previewMock/types";
import { demoThemePreview } from "./themePreview";

type Theme = ThemeEntry;
type Candidate = Omit<components["schemas"]["Candidate"], "theme"> & { theme: Theme };
type Operation = Omit<components["schemas"]["ImportRecord"], "candidates"> & {
  candidates: Candidate[];
};
type Installation = components["schemas"]["ThemeInstallation"];
export type DemoPackage = {
  source?: components["schemas"]["ThemeSource"];
  theme: Theme;
  files: Record<string, Uint8Array>;
  metadata: components["schemas"]["PackageMetadata"];
};
let generation = 0;
const packages = new Map<string, DemoPackage>();
const previewUrls = new Map<string, string>();
const history = new Map<string, DemoPackage[]>();
const operations = new Map<string, { record: Operation; packages: DemoPackage[] }>();
const receipts = new Map<string, { fingerprint: string; keys: string[] }>();
const protectedKeys = new Set(["dark", "light", "ascii", "windows95"]);

function themes(): Theme[] {
  return structuredClone(DEV_MOCK.config.themesCatalog?.themes || []) as Theme[];
}
function save(items: Theme[], defaultTheme?: string) {
  const catalog = {
    default_theme: defaultTheme || DEV_MOCK.config.themesCatalog?.default_theme || "dark",
    themes: items.map((theme) => (packages.has(theme.key) ? { ...theme, css_file: "" } : theme)),
  };
  DEV_MOCK.config.themesCatalog = catalog as PreviewThemesCatalog;
  DEV_MOCK.data.themes_catalog = structuredClone(catalog) as PreviewThemesCatalog;
}
function payload(options: RequestInit): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(String(options.body || "{}"));
    return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  } catch {
    throw { error: "invalid_payload" };
  }
}
function json(bytes?: Uint8Array): Record<string, unknown> {
  const value: unknown = JSON.parse(strFromU8(bytes || new Uint8Array()));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw { error: "invalid_theme_manifest" };
  return value as Record<string, unknown>;
}
export function readDemoZip(bytes: Uint8Array): DemoPackage[] {
  if (!bytes.length || bytes.length > 20 * 1024 * 1024) throw { error: "archive_too_large" };
  let total = 0;
  let count = 0;
  const names = new Set<string>();
  const files = unzipSync(bytes, {
    filter(file) {
      const name = file.name.replace(/\/$/, "");
      if (
        ++count > 2000 ||
        !name ||
        name.startsWith("/") ||
        /[\\:]/.test(name) ||
        [...name].some((char) => char.charCodeAt(0) < 32) ||
        name.split("/").some((part) => part === ".." || part === "." || !part)
      )
        throw { error: "unsafe_path" };
      if (names.has(name.toLowerCase())) throw { error: "duplicate_path" };
      names.add(name.toLowerCase());
      total += file.originalSize;
      if (
        file.originalSize > 10 * 1024 * 1024 ||
        total > 100 * 1024 * 1024 ||
        file.originalSize > Math.max(1, file.size) * 200
      )
        throw { error: "archive_limit" };
      return !file.name.endsWith("/");
    },
  });
  let descriptors = Object.keys(files).filter(
    (name) => name.endsWith("/theme.json") || name === "theme.json"
  );
  const index = Object.keys(files).find((name) => name.endsWith("minishop-themes.json"));
  if (index) {
    const root = index.slice(0, -"minishop-themes.json".length);
    const entries = json(files[index]).themes;
    if (!Array.isArray(entries)) throw { error: "invalid_collection" };
    descriptors = entries.map((entry) => root + String(entry.path) + "/theme.json");
  }
  if (!descriptors.length || descriptors.length > 20) throw { error: "no_themes_found" };
  return descriptors.map((name) => {
    const data = json(files[name]);
    const prefix = name.slice(0, -"theme.json".length);
    if (typeof data.key !== "string" || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(data.key))
      throw { error: "invalid_theme_manifest" };
    const themeFiles = Object.fromEntries(
      Object.entries(files)
        .filter(([file]) => file.startsWith(prefix))
        .map(([file, content]) => [file.slice(prefix.length), content])
    );
    if (Object.keys(themeFiles).some((file) => /\.(?:js|html|svg|exe|sh)$/i.test(file)))
      throw { error: "unsupported_theme_file" };
    const theme = data as Theme;
    const metadata = themeFiles["theme-package.json"]
      ? (json(themeFiles["theme-package.json"]) as components["schemas"]["PackageMetadata"])
      : {
          author: null,
          homepage: "",
          license: "",
          preview: "",
          schema_version: 1 as const,
          version: "",
        };
    return { theme, files: themeFiles, metadata };
  });
}
async function builtinPackage(key: string): Promise<DemoPackage> {
  if (!protectedKeys.has(key)) {
    const theme = themes().find((item) => item.key === key);
    if (!theme) throw { error: "theme_not_found" };
    return {
      theme,
      files: { "theme.json": strToU8(JSON.stringify(theme)) },
      metadata: {
        schema_version: 1,
        version: "",
        author: null,
        homepage: "",
        license: "",
        preview: "",
      },
    };
  }
  const bytes = new Uint8Array(
    await (await fetch("/demo/theme-starters/" + key + ".zip")).arrayBuffer()
  );
  return readDemoZip(bytes)[0];
}
function samePackage(left: DemoPackage, right: DemoPackage): boolean {
  const names = Object.keys(left.files);
  return (
    names.length === Object.keys(right.files).length &&
    names.every((name) => {
      const a = left.files[name],
        b = right.files[name];
      return b && a.length === b.length && a.every((value, index) => value === b[index]);
    })
  );
}
function installation(theme: Theme): Installation {
  const item = packages.get(theme.key);
  return {
    key: theme.key,
    protected: protectedKeys.has(theme.key),
    managed: Boolean(item),
    version: item?.metadata.version || "",
    metadata: item?.metadata || null,
    digest: "",
    modified: false,
    can_rollback: Boolean(history.get(theme.key)?.length),
    source:
      item?.source ||
      (item ? { kind: "archive", label: "ZIP", commit: "", ref: "", subdir: "", url: "" } : null),
    preview_url:
      previewUrls.get(theme.key) ||
      (!item && protectedKeys.has(theme.key)
        ? "/demo/runtime/themes/" + theme.key + "/preview.webp"
        : ""),
  };
}
export function themePackageResponse(
  path: string,
  options: RequestInit
): Promise<unknown> | undefined {
  if (path !== "/admin/themes" && !path.startsWith("/admin/themes/")) return undefined;
  return handle(path, options).catch((error: unknown) => ({
    ok: false,
    error: error && typeof error === "object" && "error" in error ? error.error : "invalid_archive",
  }));
}
async function handle(path: string, options: RequestInit): Promise<unknown> {
  const url = new URL(path, "https://demo.invalid");
  const parts = url.pathname.split("/");
  const method = options.method || "GET";
  if (url.pathname === "/admin/themes") {
    if (method === "PUT") {
      const body = payload(options);
      if (body.expected_generation !== undefined && body.expected_generation !== generation)
        throw { error: "catalog_changed" };
      const catalog = body.catalog as { themes: Theme[]; default_theme: string };
      save(catalog.themes, catalog.default_theme);
      generation++;
    }
    return {
      ok: true,
      generation,
      themes_dir: "data/themes",
      exists: true,
      catalog: structuredClone(DEV_MOCK.config.themesCatalog),
    };
  }
  if (url.pathname === "/admin/themes/library")
    return {
      ok: true,
      generation,
      writable: true,
      installations: themes()
        .filter((theme) => !theme.hidden && !theme.variant_alias_for)
        .map(installation),
    };
  if (url.pathname === "/admin/themes/imports" && method === "POST") {
    let items: DemoPackage[];
    let label: string;
    if (options.body instanceof FormData) {
      const file = options.body.get("file");
      if (!(file instanceof File)) throw { error: "archive_file_required" };
      label = file.name;
      items = readDemoZip(new Uint8Array(await file.arrayBuffer()));
    } else {
      const body = payload(options);
      const source = new URL(String(body.url));
      if (
        source.protocol !== "https:" ||
        !["github.com", "gitlab.com"].includes(source.hostname) ||
        source.username ||
        source.password ||
        source.port
      )
        throw { error: "repository_host_not_supported" };
      label = source.host + source.pathname;
      items = readDemoZip(
        new Uint8Array(await (await fetch("/demo/theme-examples.zip")).arrayBuffer())
      );
      for (const item of items)
        item.source = {
          kind: source.hostname === "github.com" ? "github" : "gitlab",
          label,
          url: String(body.url),
          ref: String(body.ref || "main"),
          subdir: String(body.subdir || ""),
          commit: "",
        };
    }
    const candidates: Candidate[] = items.map((item) => ({
      detail: "",
      digest: "",
      size: Object.values(item.files).reduce((total, bytes) => total + bytes.length, 0),
      key: item.theme.key,
      path: item.theme.key,
      theme: item.theme,
      metadata: item.metadata,
      files: Object.keys(item.files).length,
      error: protectedKeys.has(item.theme.key)
        ? "protected_theme"
        : items.filter((other) => other.theme.key === item.theme.key).length > 1
          ? "duplicate_theme_key"
          : item.metadata.compatibility?.theme_api && item.metadata.compatibility.theme_api !== 1
            ? "incompatible_theme_api"
            : "",
    }));
    const record: Operation = {
      id: crypto.randomUUID().replaceAll("-", ""),
      actor: 1,
      created_at: Date.now() / 1000,
      state: "ready",
      generation,
      error: "",
      detail: "",
      source: { kind: "archive", label, commit: "", ref: "", subdir: "", url: "" },
      candidates,
    };
    operations.set(record.id, { record, packages: items });
    return { ok: true, operation: record };
  }
  if (parts[3] === "imports") {
    const operation = operations.get(parts[4]);
    if (!operation) throw { error: "import_not_found" };
    if (Date.now() / 1000 - operation.record.created_at > 1800) throw { error: "import_expired" };
    if (parts[5] === "preview") {
      const item = operation.packages.find((item) => item.theme.key === parts[6]);
      if (!item || operation.record.state !== "ready") throw { error: "import_not_ready" };
      return demoThemePreview(item, url.searchParams.get("variant") || "dark");
    }
    if (method === "DELETE") {
      operation.record.state = "cancelled";
      return { ok: true, operation: operation.record };
    }
    if (parts[5] === "install") {
      const body = payload(options);
      const choices = body.choices as components["schemas"]["InstallChoice"][];
      const receiptKey = operation.record.id + ":" + String(body.idempotency_key);
      const fingerprint = JSON.stringify(body);
      const receipt = receipts.get(receiptKey);
      if (receipt) {
        if (receipt.fingerprint !== fingerprint) throw { error: "idempotency_conflict" };
        return { ok: true, generation, keys: receipt.keys };
      }
      if (operation.record.state !== "ready") throw { error: "import_not_ready" };
      if (body.expected_generation !== generation) throw { error: "catalog_changed" };
      const current = themes();
      for (const choice of choices) {
        const candidate = operation.record.candidates?.find((item) => item.key === choice.key);
        if (!candidate || candidate.error || protectedKeys.has(choice.key))
          throw { error: candidate?.error || "invalid_theme_selection" };
        if (current.some((theme) => theme.key === choice.key) && choice.action === "install")
          throw { error: "theme_exists" };
      }
      for (const choice of choices) {
        const item = operation.packages.find((item) => item.theme.key === choice.key);
        if (!item) continue;
        const previous = packages.get(choice.key);
        if (previous && !samePackage(previous, item))
          history.set(choice.key, [previous, ...(history.get(choice.key) || [])].slice(0, 5));
        packages.set(choice.key, structuredClone(item));
        const existing = current.findIndex((theme) => theme.key === choice.key);
        if (existing >= 0)
          current[existing] = {
            ...item.theme,
            ...current[existing],
            tokens: { ...item.theme.tokens, ...current[existing].tokens },
          };
        else current.push({ ...item.theme, default: false, use_in_admin: false });
      }
      save(current);
      generation++;
      operation.record.state = "installed";
      const keys = choices.map((choice) => choice.key);
      receipts.set(receiptKey, { fingerprint, keys });
      return { ok: true, generation, keys };
    }
    return { ok: true, operation: operation.record };
  }
  if (parts[3] === "library" && parts[4]) {
    const key = decodeURIComponent(parts[4]);
    if (parts[5] === "preview") {
      if (method === "POST") {
        previewUrls.set(key, "/demo/runtime/themes/" + key + "/preview.webp?custom=1");
        generation++;
        return { ok: true, preview_url: previewUrls.get(key) };
      }
      const item = packages.get(key) || (await builtinPackage(key));
      const current = themes().find((theme) => theme.key === key);
      return demoThemePreview(
        { ...item, theme: { ...item.theme, ...current, css_file: item.theme.css_file } },
        url.searchParams.get("variant") || "dark"
      );
    }
    const body = payload(options);
    if (body.expected_generation !== generation) throw { error: "catalog_changed" };
    if (protectedKeys.has(key)) throw { error: "protected_theme" };
    if (method === "DELETE") {
      if (DEV_MOCK.config.themesCatalog?.default_theme === key) throw { error: "active_theme" };
      packages.delete(key);
      save(themes().filter((theme) => theme.key !== key));
    } else if (parts[5] === "rollback") {
      const previous = history.get(key)?.shift();
      if (!previous) throw { error: "no_previous_version" };
      const current = packages.get(key);
      if (current) history.get(key)?.unshift(current);
      packages.set(key, previous);
      save(themes().map((theme) => (theme.key === key ? { ...previous.theme, ...theme } : theme)));
    }
    generation++;
    return { ok: true, generation, keys: [key] };
  }
  if (url.pathname === "/admin/themes/export") {
    const body = payload(options);
    const output: Record<string, Uint8Array> = {};
    for (const key of body.keys as string[]) {
      const item = packages.get(key) || (await builtinPackage(key));
      const newKey = String(body.new_key || key);
      if (body.new_key && (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(newKey) || protectedKeys.has(newKey)))
        throw { error: "protected_theme" };
      for (const [name, bytes] of Object.entries(item.files)) {
        let content = bytes;
        if (name === "theme.json") {
          const theme = body.include_overrides
            ? themes().find((theme) => theme.key === key) || item.theme
            : item.theme;
          content = strToU8(
            JSON.stringify({ ...theme, key: newKey, default: false, use_in_admin: false }, null, 2)
          );
        } else if (name.endsWith(".css") && newKey !== key) {
          content = strToU8(strFromU8(bytes).replaceAll("theme-key-" + key, "theme-key-" + newKey));
        }
        output[newKey + "/" + name] = content;
      }
    }
    return new Blob([new Uint8Array(zipSync(output)).buffer], { type: "application/zip" });
  }
  throw { error: "not_found" };
}

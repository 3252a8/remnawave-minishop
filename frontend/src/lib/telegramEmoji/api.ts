import { createApiClient, unwrap, type ApiClient, type GetResponse } from "$lib/webapp/publicApi";
import {
  clearEmojiCatalogStorage,
  emojiApiCacheScope,
  emojiCatalogGeneration,
  readEmojiCatalog,
  writeEmojiCatalog,
} from "$lib/webapp/emojiCatalogStorage";
import type {
  EmojiCatalog,
  EmojiLibrary,
  MenuAppearance,
  MenuConfiguration,
  MenuPreview,
  MenuPreviewRequest,
  MenuTestResult,
} from "./types";
import {
  buildTelegramEmojiAdminPath,
  buildTelegramEmojiCatalogPath,
  buildTelegramEmojiLibraryPath,
  buildTelegramEmojiRefreshPath,
  buildTelegramMenuPath,
  buildTelegramMenuPreviewPath,
  buildTelegramMenuTestPath,
} from "./paths";

export type TelegramEmojiApi = ApiClient["api"];
export type TelegramEmojiMediaApi = ApiClient["apiBlob"];
const defaultClient = createApiClient();
export const defaultTelegramEmojiApi = defaultClient.api;
export const defaultTelegramEmojiMediaApi = defaultClient.apiBlob;

type MenuWireResponse = Extract<GetResponse<"/api/admin/telegram-menu">, { ok: true }>;
function menuConfiguration(response: MenuWireResponse): MenuConfiguration {
  return {
    appearance: { schema_version: 1, buttons: response.appearance.buttons || {} },
    revision: response.revision,
    buttons: response.buttons.map((button) => ({ ...button, label: button.label || undefined })),
    languages: response.languages
      .filter((language) => Boolean(language.code))
      .map((language) => ({ code: language.code, name: language.name || language.code })),
    capabilities: {
      icon: response.capabilities.icon || { state: "unknown", tested_at: null },
      text: response.capabilities.text || { state: "unknown", tested_at: null },
    },
  };
}

export async function getEmojiLibrary(
  api: TelegramEmojiApi,
  signal?: AbortSignal
): Promise<EmojiLibrary> {
  return unwrap(await api(buildTelegramEmojiLibraryPath(), { signal })) as EmojiLibrary;
}

export async function importEmojiSource(
  api: TelegramEmojiApi,
  source: string,
  expectedRevision: string
): Promise<EmojiLibrary> {
  clearEmojiCatalogStorage();
  return unwrap(
    await api(buildTelegramEmojiLibraryPath(), {
      method: "POST",
      body: JSON.stringify({ source, expected_revision: expectedRevision }),
    })
  ) as EmojiLibrary;
}

export async function removeEmojiSource(
  api: TelegramEmojiApi,
  source: string,
  expectedRevision: string
): Promise<EmojiLibrary> {
  clearEmojiCatalogStorage();
  return unwrap(
    await api(buildTelegramEmojiLibraryPath(), {
      method: "DELETE",
      body: JSON.stringify({ source, expected_revision: expectedRevision }),
    })
  ) as EmojiLibrary;
}

export async function refreshEmojiSource(
  api: TelegramEmojiApi,
  source: string
): Promise<EmojiLibrary> {
  clearEmojiCatalogStorage();
  return unwrap(
    await api(buildTelegramEmojiRefreshPath(), {
      method: "POST",
      body: JSON.stringify({ source }),
    })
  ) as EmojiLibrary;
}

export async function getEmojiCatalog(
  api: TelegramEmojiApi,
  query: { set?: string; q?: string; offset?: number; ids?: string[] } = {},
  signal?: AbortSignal,
  onRefresh?: (catalog: EmojiCatalog) => void
): Promise<EmojiCatalog> {
  const params = new URLSearchParams({ offset: String(query.offset ?? 0), limit: "60" });
  if (query.set) params.set("set", query.set);
  if (query.q) params.set("q", query.q);
  if (query.ids?.length) params.set("ids", query.ids.join(","));
  const scope = emojiApiCacheScope(api);
  const generation = emojiCatalogGeneration();
  const key = params.toString();
  const request = async () => {
    const result = unwrap(
      await api(buildTelegramEmojiCatalogPath(params), { signal })
    ) as EmojiCatalog;
    if (
      signal?.aborted ||
      emojiApiCacheScope(api) !== scope ||
      emojiCatalogGeneration() !== generation
    )
      throw new DOMException("The session changed", "AbortError");
    if (scope) writeEmojiCatalog(scope, key, result, generation);
    return result;
  };
  const cached = onRefresh && scope ? await readEmojiCatalog(scope, key) : null;
  if (
    signal?.aborted ||
    emojiApiCacheScope(api) !== scope ||
    emojiCatalogGeneration() !== generation
  )
    throw new DOMException("The session changed", "AbortError");
  if (cached) {
    void request()
      .then((catalog) => onRefresh?.(catalog))
      .catch((failure: unknown) => {
        if (
          failure &&
          typeof failure === "object" &&
          "status" in failure &&
          (failure.status === 401 || failure.status === 403)
        )
          clearEmojiCatalogStorage();
      });
    return cached;
  }
  return request();
}

export async function getEmojiAdminId(api: TelegramEmojiApi): Promise<string> {
  const result = unwrap(await api(buildTelegramEmojiAdminPath()));
  return "user_id" in result ? String(result.user_id) : "";
}

export async function getMenuConfiguration(api: TelegramEmojiApi): Promise<MenuConfiguration> {
  return menuConfiguration(unwrap(await api(buildTelegramMenuPath())));
}

export async function saveMenuAppearance(
  api: TelegramEmojiApi,
  appearance: MenuAppearance,
  expectedRevision: string
): Promise<MenuConfiguration> {
  return menuConfiguration(
    unwrap(
      await api(buildTelegramMenuPath(), {
        method: "PUT",
        body: JSON.stringify({ appearance, expected_revision: expectedRevision }),
      })
    )
  );
}

export async function getMenuPreview(
  api: TelegramEmojiApi,
  draft: MenuPreviewRequest,
  signal?: AbortSignal
): Promise<MenuPreview> {
  return unwrap(
    await api(buildTelegramMenuPreviewPath(), {
      method: "POST",
      body: JSON.stringify(draft),
      signal,
    })
  ) as MenuPreview;
}

export async function sendMenuTest(
  api: TelegramEmojiApi,
  draft: MenuPreviewRequest
): Promise<MenuTestResult> {
  return unwrap(
    await api(buildTelegramMenuTestPath(), { method: "POST", body: JSON.stringify(draft) })
  ) as MenuTestResult;
}

export function telegramEmojiErrorCode(failure: unknown, fallback: string): string {
  if (failure && typeof failure === "object") {
    const payload =
      "payload" in failure && failure.payload && typeof failure.payload === "object"
        ? failure.payload
        : failure;
    const code = "error" in payload ? String(payload.error) : "";
    if (/^telegram_(?:emoji|menu)_[a-z_]+$/.test(code)) return code;
  }
  return fallback;
}

export function emojiSelectionKey(item: { id: string; fallback: string }): string {
  return item.id || `unicode:${item.fallback}`;
}

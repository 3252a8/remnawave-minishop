import en from "../../../../../locales/en.json";
import ru from "../../../../../locales/ru.json";
import { parseMenuButtonDrafts } from "../../admin/menuButtons";
import type {
  ButtonStyle,
  EmojiCapabilities,
  EmojiItem,
  EmojiLibrary,
  MenuAppearance,
  MenuConfiguration,
  MenuPreview,
  MenuPreviewButton,
  MenuScenario,
  MenuScreen,
} from "../../telegramEmoji/types";
import { DEV_MOCK } from "../previewMock";
import { DATASET } from "./dataset";
import { demoSettingsChanges } from "./state";

const locale = (language: string): Record<string, string> => (language === "ru" ? ru : en);
const translate = (language: string, key: string): string => locale(language)[key] || key;
const glyphs = ["🚀", "💎", "🔥", "⭐", "💙", "🎉", "✅", "🛡️", "⚡", "🎁", "🔑", "🌐"];
let appearance: MenuAppearance = { schema_version: 1, buttons: {} };
let menuRevision = 0;
let libraryRevision = 0;
let packs = ["MinishopDemo"];
let manualIds: string[] = [];
let capabilities: EmojiCapabilities = {
  icon: { state: "unknown", tested_at: null },
  text: { state: "unknown", tested_at: null },
};

function emoji(id: string, index: number, setName: string | null): EmojiItem {
  return {
    id,
    fallback: glyphs[index % glyphs.length],
    set_name: setName,
    thumbnail_url: null,
    format: index % 3 === 0 ? "animated" : "static",
  };
}
function allEmoji(): EmojiItem[] {
  return [
    ...packs.flatMap((pack, packIndex) =>
      Array.from({ length: 84 }, (_, index) =>
        emoji(String(5368324170671202286n + BigInt(packIndex * 100 + index)), index, pack)
      )
    ),
    ...manualIds.map((id, index) => emoji(id, index, null)),
  ];
}
function library(): EmojiLibrary {
  return {
    library: { schema_version: 1, sets: [...packs], manual_ids: [...manualIds] },
    revision: String(libraryRevision),
    sets: packs.map((name) => ({ name, title: name, count: 84, state: "ready" })),
  };
}
function customButtons() {
  const override = demoSettingsChanges.get("MENU_BUTTONS_JSON");
  const field = DATASET.settingsSections
    ?.flatMap((section) => section.fields || [])
    .find((item) => item.key === "MENU_BUTTONS_JSON");
  return parseMenuButtonDrafts(override?.deleted ? "" : (override?.value ?? field?.value ?? ""))
    .buttons;
}
const registry = [
  ["personal_account", "menu_personal_account_button", "🔑", ["main", "bot"]],
  ["trial", "menu_activate_trial_button", "🆓", ["main", "bot"]],
  ["bot_interface", "menu_bot_interface_button", "🤖", ["main"]],
  ["subscribe", "menu_subscribe_inline", "🚀", ["bot"]],
  ["my_subscription", "menu_my_subscription_inline", "🔐", ["bot"]],
  ["payment_history", "menu_payment_history_button", "💳", ["bot"]],
  ["promo", "menu_apply_promo_button", "🎟", ["bot"]],
  ["referral", "menu_referral_inline", "🎁", ["bot"]],
  ["language", "menu_language_settings_inline", "🌐", ["bot"]],
  ["server_status", "menu_server_status_button", "", ["main", "bot"]],
  ["support", "menu_support_button", "💬", ["main", "bot"]],
  ["information", "menu_info_button", "ℹ️", ["main", "bot"]],
  ["back_to_main", "admin_telegram_menu_button_back_to_main", "", ["bot", "information"]],
  ["privacy", "admin_telegram_menu_button_privacy", "", ["information"]],
  ["user_agreement", "admin_telegram_menu_button_user_agreement", "", ["information"]],
] satisfies [string, string, string, string[]][];

function configuration(language = "ru"): MenuConfiguration {
  return {
    appearance: structuredClone(appearance),
    revision: String(menuRevision),
    capabilities,
    languages: [
      { code: "ru", name: "Русский" },
      { code: "en", name: "English" },
    ],
    buttons: [
      ...registry.map(([id, label_key, emoji_fallback, screens]) => ({
        id,
        label_key,
        emoji_fallback,
        screens,
        label: translate(language, label_key),
      })),
      ...customButtons().map((button) => ({
        id: `custom:${button.id}`,
        label_key: "",
        label: button.labels[language] || button.labels.en || button.id,
        emoji_fallback: button.telegram_emoji,
        screens: button.show_in_bot ? ["main", "bot"] : [],
      })),
    ],
  };
}
function preview(
  draft: MenuAppearance,
  screen: MenuScreen,
  language: string,
  scenario: MenuScenario
): MenuPreview {
  const buttons = configuration(language).buttons.filter((button) =>
    button.screens.includes(screen)
  );
  const hidden: MenuPreview["hidden"] = [];
  const items = buttons.flatMap((button): MenuPreviewButton[] => {
    let reason = "";
    if (button.id === "trial" && (scenario !== "new" || DEV_MOCK.config.trialEnabled === false))
      reason = translate(language, "admin_telegram_menu_demo_trial_hidden");
    if (button.id === "my_subscription" && scenario !== "active")
      reason = translate(language, "admin_telegram_menu_demo_subscription_hidden");
    if (button.id === "referral" && DEV_MOCK.config.referralProgramEnabled === false)
      reason = translate(language, "admin_telegram_menu_demo_referral_hidden");
    if (reason) {
      hidden.push({ id: button.id, label: button.label || button.id, reason });
      return [];
    }
    const value = draft.buttons[button.id];
    const mode = value?.icon_mode || (value?.icon_custom_emoji_id ? "custom" : "inherit");
    const iconId = mode === "custom" ? value?.icon_custom_emoji_id || null : null;
    const custom = customButtons().find((item) => `custom:${item.id}` === button.id);
    const label = button.label || button.id;
    const decorated =
      button.emoji_fallback && label.startsWith(button.emoji_fallback)
        ? label.slice(button.emoji_fallback.length).trimStart()
        : label;
    const kind = custom
      ? custom.kind === "webapp" || custom.kind === "page"
        ? "webapp"
        : "url"
      : ["personal_account", "payment_history"].includes(button.id)
        ? "webapp"
        : ["support", "server_status", "privacy", "user_agreement"].includes(button.id)
          ? "url"
          : "callback";
    return [
      {
        id: button.id,
        label: mode === "none" || iconId ? decorated : label,
        style: value?.style || "default",
        icon_custom_emoji_id: iconId,
        emoji_fallback:
          allEmoji().find((item) => item.id === iconId)?.fallback || button.emoji_fallback,
        thumbnail_url: null,
        kind,
        target: custom?.target || (button.id === "payment_history" ? "payment-history" : button.id),
      },
    ];
  });
  const rows: MenuPreviewButton[][] = [];
  for (let index = 0; index < items.length; index += 2) rows.push(items.slice(index, index + 2));
  return {
    text: translate(
      language,
      screen === "information"
        ? "admin_telegram_menu_demo_information"
        : "admin_telegram_menu_demo_message"
    ),
    rows,
    hidden,
    available: true,
  };
}
function body(options: RequestInit): Record<string, unknown> {
  if (typeof options.body !== "string") return {};
  try {
    const value: unknown = JSON.parse(options.body);
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}
function readAppearance(value: unknown): MenuAppearance | null {
  if (
    !value ||
    typeof value !== "object" ||
    !("schema_version" in value) ||
    value.schema_version !== 1 ||
    !("buttons" in value) ||
    !value.buttons ||
    typeof value.buttons !== "object"
  )
    return null;
  const buttons: MenuAppearance["buttons"] = {};
  for (const [id, entry] of Object.entries(value.buttons)) {
    if (
      !entry ||
      typeof entry !== "object" ||
      !("style" in entry) ||
      typeof entry.style !== "string" ||
      !["default", "primary", "success", "danger"].includes(entry.style)
    )
      return null;
    const icon =
      "icon_custom_emoji_id" in entry && typeof entry.icon_custom_emoji_id === "string"
        ? entry.icon_custom_emoji_id
        : null;
    const mode =
      "icon_mode" in entry && (entry.icon_mode === "custom" || entry.icon_mode === "none")
        ? entry.icon_mode
        : "inherit";
    buttons[id] = {
      style: entry.style as ButtonStyle,
      icon_custom_emoji_id: icon,
      icon_mode: mode,
    };
  }
  return { schema_version: 1, buttons };
}

export function telegramMenuDemoResponse(path: string, options: RequestInit): unknown | undefined {
  const url = new URL(path, "https://demo.invalid");
  const route = url.pathname.replace(/^\/api/, "");
  const method = String(options.method || "GET").toUpperCase();
  const payload = body(options);
  const fail = (error: string) => ({ ok: false, error });
  if (route === "/admin/me") {
    const user_id = Number(DEV_MOCK.data.user?.id || DEV_MOCK.data.user?.user_id) || 3252001;
    return { ok: true, user_id, admin_ids: [user_id] };
  }
  if (route === "/admin/telegram-menu") {
    if (method === "PUT") {
      if (payload.expected_revision !== String(menuRevision))
        return fail("telegram_menu_revision_conflict");
      const updated = readAppearance(payload.appearance);
      if (!updated) return fail("telegram_menu_invalid_appearance");
      appearance = updated;
      menuRevision += 1;
    }
    return { ok: true, ...configuration() };
  }
  if (route === "/admin/telegram-menu/preview" || route === "/admin/telegram-menu/test") {
    const draft = readAppearance(payload.appearance);
    if (!draft) return fail("telegram_menu_invalid_appearance");
    if (route.endsWith("/test")) {
      const tested_at = new Date().toISOString();
      capabilities = {
        icon: { state: "supported", tested_at },
        text: { state: "supported", tested_at },
      };
      return { ok: true, sent: true, capabilities, message_id: 1 };
    }
    const screen: MenuScreen =
      payload.screen === "bot" || payload.screen === "information" ? payload.screen : "main";
    const scenario: MenuScenario =
      payload.scenario === "active" || payload.scenario === "trial_unavailable"
        ? payload.scenario
        : "new";
    return { ok: true, ...preview(draft, screen, String(payload.language || "ru"), scenario) };
  }
  if (
    route === "/admin/telegram-emoji/library" ||
    route === "/admin/telegram-emoji/library/refresh"
  ) {
    if (method !== "GET") {
      const source = String(payload.source || "").trim();
      if (!route.endsWith("/refresh") && payload.expected_revision !== String(libraryRevision))
        return fail("telegram_emoji_revision_conflict");
      let name = source;
      if (source.startsWith("https://")) {
        const parsed = new URL(source);
        if (parsed.hostname !== "t.me" || !/^\/addemoji\/[A-Za-z0-9_]+\/?$/.test(parsed.pathname))
          return fail("telegram_emoji_invalid_source");
        name = parsed.pathname.split("/")[2];
      }
      if (!/^[A-Za-z0-9_]+$/.test(name)) return fail("telegram_emoji_invalid_source");
      if (method === "DELETE") {
        packs = packs.filter((pack) => pack !== name);
        manualIds = manualIds.filter((id) => id !== name);
      } else if (/^\d+$/.test(name)) {
        if (name.length < 10) return fail("telegram_emoji_invalid_id");
        manualIds = [...new Set([...manualIds, name])];
      } else if (!route.endsWith("/refresh")) packs = [...new Set([...packs, name])];
      libraryRevision += 1;
    }
    return { ok: true, ...library() };
  }
  if (route === "/admin/telegram-emoji/catalog") {
    const selectedSet = url.searchParams.get("set");
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const ids = new Set((url.searchParams.get("ids") || "").split(",").filter(Boolean));
    const values = ids.size ? [...ids].map((id, index) => emoji(id, index, null)) : allEmoji();
    const filtered = values.filter(
      (item) =>
        (!selectedSet || item.set_name === selectedSet) &&
        (!q || `${item.id} ${item.fallback} ${item.set_name || ""}`.toLowerCase().includes(q))
    );
    const offset = Math.max(0, Number(url.searchParams.get("offset") || 0));
    const limit = Math.min(60, Number(url.searchParams.get("limit") || 60));
    return {
      ok: true,
      items: filtered.slice(offset, offset + limit),
      total: filtered.length,
      offset,
      limit,
    };
  }
  return undefined;
}

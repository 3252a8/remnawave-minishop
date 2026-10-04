export type TranslateFn = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;

export type EmojiItem = {
  /** Decimal Telegram IDs stay strings. An empty ID denotes an ordinary Unicode emoji. */
  id: string;
  fallback: string;
  set_name: string | null;
  thumbnail_url: string | null;
  format: "static" | "animated" | "video";
};

export type EmojiLibrary = {
  library: { schema_version: 1; sets: string[]; manual_ids: string[] };
  revision: string;
  sets: {
    name: string;
    title: string;
    count: number;
    state: "ready" | "warming" | "partial" | "error" | "unknown";
    cached_count?: number;
    preview_count?: number;
  }[];
};

export type EmojiCatalog = {
  items: EmojiItem[];
  total: number;
  offset: number;
  limit: number;
};

export type ButtonStyle = "default" | "primary" | "success" | "danger";
export type IconMode = "inherit" | "none" | "custom";
export type ButtonAppearance = {
  style: ButtonStyle;
  icon_custom_emoji_id: string | null;
  icon_mode?: IconMode;
};
export type MenuAppearance = {
  schema_version: 1;
  buttons: Record<string, ButtonAppearance>;
};
export type EmojiCapability = {
  state: "unknown" | "supported" | "unavailable";
  tested_at: string | null;
};
export type EmojiCapabilities = { icon: EmojiCapability; text: EmojiCapability };
export type MenuScreen = "main" | "bot" | "information";
export type MenuScenario = "new" | "active" | "trial_unavailable";
export type MenuPreviewRequest = {
  appearance: MenuAppearance;
  screen: MenuScreen;
  language: string;
  scenario: MenuScenario;
};
export type MenuConfiguration = {
  appearance: MenuAppearance;
  revision: string;
  buttons: {
    id: string;
    label_key: string;
    label?: string;
    screens: string[];
    emoji_fallback: string;
  }[];
  languages: { code: string; name: string }[];
  capabilities: EmojiCapabilities;
};
export type MenuPreviewButton = {
  id: string;
  label: string;
  style: ButtonStyle;
  icon_custom_emoji_id: string | null;
  emoji_fallback: string;
  thumbnail_url: string | null;
  kind: "callback" | "url" | "webapp";
  target: string;
};
export type MenuPreview = {
  text: string;
  rows: MenuPreviewButton[][];
  hidden: { id: string; label: string; reason: string }[];
  available: boolean;
};
export type MenuTestResult = {
  sent: boolean;
  capabilities: EmojiCapabilities;
  message_id: number | null;
};

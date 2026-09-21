export type InstallGuideRecord = Record<string, unknown>;

type NavigatorLike = {
  userAgent?: string;
  userAgentData?: { platform?: string };
};
type TemplateContext = {
  subscription?: InstallGuideRecord;
  user?: InstallGuideRecord;
};
type InstallGuideButton = InstallGuideRecord & {
  link?: unknown;
  type?: unknown;
  action?: unknown;
};
export type InstallGuideButtonAction =
  { kind: "copy"; value: string } | { kind: "open"; value: string };

const colorTokens: Record<string, string> = {
  amber: "#f59e0b",
  blue: "#3b82f6",
  cyan: "#06b6d4",
  emerald: "#10b981",
  fuchsia: "#d946ef",
  gray: "#6b7280",
  green: "#22c55e",
  indigo: "#6366f1",
  lime: "#84cc16",
  neutral: "#737373",
  orange: "#f97316",
  pink: "#ec4899",
  purple: "#a855f7",
  red: "#ef4444",
  rose: "#f43f5e",
  sky: "#0ea5e9",
  slate: "#64748b",
  stone: "#78716c",
  teal: "#14b8a6",
  violet: "#8b5cf6",
  yellow: "#eab308",
  zinc: "#71717a",
};

export function localizedInstallValue(value: unknown, currentLang: string, fallback = ""): string {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return fallback;
  const record = value as InstallGuideRecord;
  const lang = String(currentLang || "ru")
    .split("-")[0]
    .toLowerCase();
  return (
    stringValue(record[lang]) ||
    stringValue(record.ru) ||
    stringValue(record.en) ||
    stringValue(Object.values(record).find((item) => typeof item === "string" && item.trim())) ||
    fallback
  );
}

export function installIconColorStyle(color: unknown): string {
  const raw = String(color || "").trim();
  const value = colorTokens[raw] || raw;
  return value ? `--install-icon-color:${value};` : "";
}

export function detectInstallPlatformKey(
  availableKeys: string[],
  telegramPlatform = "",
  nav: NavigatorLike | null = typeof navigator === "undefined" ? null : (navigator as NavigatorLike)
): string {
  const available = new Set(availableKeys || []);
  const tgPlatform = String(telegramPlatform || "").toLowerCase();
  const userAgentDataPlatform = String(nav?.userAgentData?.platform || "").toLowerCase();
  const ua = String(nav?.userAgent || "").toLowerCase();
  const candidates = [];

  if (tgPlatform.includes("ios")) candidates.push("ios");
  if (tgPlatform.includes("android")) candidates.push("android");
  if (tgPlatform.includes("mac")) candidates.push("macos");
  if (tgPlatform.includes("windows")) candidates.push("windows");
  if (tgPlatform.includes("linux")) candidates.push("linux");

  if (userAgentDataPlatform.includes("android")) candidates.push("android");
  if (userAgentDataPlatform.includes("ios")) candidates.push("ios");
  if (userAgentDataPlatform.includes("mac")) candidates.push("macos");
  if (userAgentDataPlatform.includes("win")) candidates.push("windows");
  if (userAgentDataPlatform.includes("linux")) candidates.push("linux");

  if (ua.includes("apple tv")) candidates.push("appleTV");
  if (ua.includes("android") && /\btv\b|aft|bravia|shield/i.test(ua)) candidates.push("androidTV");
  if (/iphone|ipad|ipod/.test(ua)) candidates.push("ios");
  if (ua.includes("android")) candidates.push("android");
  if (ua.includes("windows")) candidates.push("windows");
  if (ua.includes("macintosh") || ua.includes("mac os")) candidates.push("macos");
  if (ua.includes("linux") || ua.includes("x11")) candidates.push("linux");

  return candidates.find((candidate) => available.has(candidate)) || "";
}

export function resolveInstallTemplate(
  value: unknown,
  { subscription = {}, user = {} }: TemplateContext
): string {
  const subscriptionLink =
    stringValue(subscription.config_link) || stringValue(subscription.connect_url);
  const httpLink =
    subscription.link_mode === "minishop"
      ? stringValue(subscription.http_url) || subscriptionLink
      : subscriptionLink;
  const username =
    stringValue(user.username) || stringValue(user.first_name) || stringValue(user.id);
  const replacements: Record<string, string> = {
    HAPP_CRYPT3_LINK: subscriptionLink,
    HAPP_CRYPT4_LINK: subscriptionLink,
    SUBSCRIPTION_LINK: httpLink,
    USERNAME: username,
  };
  return String(value || "").replace(/\{\{\s*([A-Z0-9_]+)\s*\}\}/g, (_match, key) =>
    Object.prototype.hasOwnProperty.call(replacements, key) ? replacements[key] : ""
  );
}

export function resolveInstallButtonAction(
  button: InstallGuideButton,
  context: TemplateContext
): InstallGuideButtonAction {
  const action =
    button?.action && typeof button.action === "object"
      ? (button.action as InstallGuideRecord)
      : null;
  const target =
    action?.target && typeof action.target === "object"
      ? (action.target as InstallGuideRecord)
      : null;
  if (target) {
    let value = "";
    if (target.kind === "resource" && target.resourceId === "primary-subscription") {
      value =
        target.representation === "http"
          ? resolveInstallTemplate("{{SUBSCRIPTION_LINK}}", context)
          : resolveInstallTemplate("{{HAPP_CRYPT4_LINK}}", context);
    } else if (target.kind === "literal") {
      value = resolveInstallTemplate(target.value, context);
    }
    return action?.kind === "copy" ? { kind: "copy", value } : { kind: "open", value };
  }
  const value = resolveInstallTemplate(button?.link, context);
  return button?.type === "copyButton" ? { kind: "copy", value } : { kind: "open", value };
}

export async function renderInstallQrDataUrl(
  value: unknown,
  render: (link: string) => Promise<string>
): Promise<string> {
  const link = String(value || "").trim();
  if (!link) return "";
  try {
    return await render(link);
  } catch (_error) {
    return "";
  }
}

export function isUnsafeInstallUrl(value: unknown): boolean {
  const url = String(value || "")
    .trim()
    .toLowerCase();
  return !url || hasControlChars(url) || /^(javascript|data|vbscript):/.test(url);
}

function hasControlChars(value: unknown): boolean {
  return Array.from(String(value || "")).some((char) => {
    const code = char.charCodeAt(0);
    return code <= 31 || code === 127;
  });
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

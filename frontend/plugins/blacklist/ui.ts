import en from "../../../backend/bot/plugins/builtin/blacklist/locales/en.json";
import ru from "../../../backend/bot/plugins/builtin/blacklist/locales/ru.json";
import { ApiError } from "./api";
import type { Reason } from "./api";

const prefix = "admin_minishop_blacklist_";
type Key = keyof typeof en;
type Copy = Key extends `${typeof prefix}${infer Word}` ? Word : never;
type Values = Record<string, string | number>;
type HostTranslate = (key: string, values?: Values, fallback?: string) => string;
export type Translate = (copy: Copy, values?: Values) => string;

export interface Props {
  currentLang?: string;
  at?: HostTranslate;
  routePrefix?: string;
  active?: boolean;
  user?: { telegram_id?: number | string | null } | null;
  userDetail?: { user?: Props["user"] } | null;
  context?: { ticket?: { user?: Props["user"] } | null };
}

export interface View {
  update(props: Props): void;
  destroy(): void;
}

const dictionaries: Record<"ru" | "en", Record<Key, string>> = { en, ru };

export function language(props: Props): "ru" | "en" {
  const language = props.currentLang || document.documentElement.lang || "en";
  return language.toLowerCase().split("-")[0] === "ru" ? "ru" : "en";
}

export function translator(props: Props): Translate {
  const messages = dictionaries[language(props)];
  return (copy, values = {}) => {
    const key: Key = `${prefix}${copy}`;
    const fallback = messages[key].replace(/\{(\w+)\}/g, (match, name: string) =>
      String(values[name] ?? match)
    );
    const hostKey = key.slice("admin_".length);
    const translated = props.at?.(hostKey, values, fallback);
    return translated && translated !== hostKey && translated !== key ? translated : fallback;
  };
}

const settingErrors = [
  "invalid_sources",
  "invalid_refresh_hours",
  "invalid_display",
  "invalid_chat_id",
  "invalid_topic_id",
  "invalid_events",
  "chat_required",
] as const;

export function errorText(
  t: Translate,
  error: unknown,
  fallback: "request_failed" | "save_failed"
): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.code === "csrf_failed") return t("session_expired");
    if (error.status === 403) return t("forbidden");
    const code = settingErrors.find((code) => code === error.code);
    if (code) return t(code);
  }
  return t(fallback);
}

export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function root(target: HTMLElement): HTMLElement {
  const node = element("section", undefined, "minishop-blacklist");
  target.append(node);
  return node;
}

export function button(text: string, action?: () => void): HTMLButtonElement {
  const node = element("button", text, "blacklist-button");
  node.type = "button";
  if (action) node.addEventListener("click", action);
  return node;
}

export function stateMessage(text: string, role: "status" | "alert" = "status"): HTMLElement {
  const node = element("p", text, role === "alert" ? "blacklist-error" : "blacklist-muted");
  node.setAttribute("role", role);
  return node;
}

export function errorState(t: Translate, error: unknown, retry: () => void): HTMLElement {
  const node = element("div", undefined, "blacklist-message");
  node.append(
    stateMessage(errorText(t, error, "request_failed"), "alert"),
    button(t("retry"), retry)
  );
  return node;
}

export function cross(label?: string): HTMLElement {
  const node = element("span", "×", "blacklist-cross");
  if (label) {
    node.setAttribute("aria-label", label);
    node.setAttribute("role", "img");
  } else {
    node.setAttribute("aria-hidden", "true");
  }
  return node;
}

function sourceLink(value: string, t: Translate): HTMLAnchorElement | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
  const link = element("a", "↗", "blacklist-source-link");
  const label = t("evidence", { host: url.host });
  link.href = url.href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = label;
  link.setAttribute("aria-label", label);
  return link;
}

export function reasonList(reasons: Reason[], t: Translate): HTMLUListElement {
  const node = element("ul", undefined, "blacklist-reasons");
  for (const reason of reasons) {
    const item = element("li");
    if (reason.text) item.append(element("span", reason.text));
    for (const url of reason.links) {
      const link = sourceLink(url, t);
      if (link) item.append(link);
    }
    if (item.childNodes.length) node.append(item);
  }
  return node;
}

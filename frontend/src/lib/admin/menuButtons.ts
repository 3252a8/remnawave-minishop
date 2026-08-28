export const MAX_MENU_BUTTONS = 20;

export type MenuButtonKind = "external" | "telegram" | "webapp";

export type MenuButtonDraft = {
  id: string;
  kind: MenuButtonKind;
  target: string;
  icon: string;
  labels: Record<string, string>;
  show_in_bot: boolean;
  show_in_webapp: boolean;
};

export type MenuButtonsParseResult = {
  buttons: MenuButtonDraft[];
  invalid: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeLabels(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([language, label]) => [
        language.trim().toLowerCase().replaceAll("_", "-"),
        String(label || ""),
      ])
      .filter(([language]) => Boolean(language))
  );
}

function normalizeButton(value: unknown): MenuButtonDraft | null {
  if (!isRecord(value)) return null;
  const kind = String(value.kind || "external") as MenuButtonKind;
  if (!(["external", "telegram", "webapp"] as string[]).includes(kind)) return null;
  const id = String(value.id || "").trim();
  if (!id) return null;
  return {
    id,
    kind,
    target: String(value.target || ""),
    icon: String(value.icon || ""),
    labels: normalizeLabels(value.labels),
    show_in_bot: typeof value.show_in_bot === "boolean" ? value.show_in_bot : true,
    show_in_webapp: typeof value.show_in_webapp === "boolean" ? value.show_in_webapp : true,
  };
}

export function parseMenuButtonDrafts(value: unknown): MenuButtonsParseResult {
  const text = String(value || "").trim();
  if (!text) return { buttons: [], invalid: false };
  try {
    const payload: unknown = JSON.parse(text);
    if (!Array.isArray(payload)) return { buttons: [], invalid: true };
    const buttons = payload.map(normalizeButton);
    if (buttons.some((button) => button === null)) return { buttons: [], invalid: true };
    return { buttons: buttons as MenuButtonDraft[], invalid: false };
  } catch {
    return { buttons: [], invalid: true };
  }
}

export function serializeMenuButtonDrafts(buttons: MenuButtonDraft[]): string {
  return JSON.stringify(buttons, null, 2);
}

export function createMenuButtonDraft(languages: string[]): MenuButtonDraft {
  const randomId = globalThis.crypto?.randomUUID?.().replaceAll("-", "");
  const fallbackId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  return {
    id: `menu_${randomId || fallbackId}`,
    kind: "external",
    target: "",
    icon: "ExternalLink",
    labels: Object.fromEntries(languages.map((language) => [language, ""])),
    show_in_bot: true,
    show_in_webapp: true,
  };
}

export function reorderMenuButtonDrafts(
  buttons: MenuButtonDraft[],
  from: number,
  to: number
): MenuButtonDraft[] {
  const next = [...buttons];
  const [moved] = next.splice(from, 1);
  if (!moved) return buttons;
  next.splice(to, 0, moved);
  return next;
}

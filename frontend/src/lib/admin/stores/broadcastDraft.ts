import { normalizeMessageButtonLink } from "$lib/admin/messageButtonTargets.js";
import type { components } from "../../api/openapi.generated";
import type { GetResponse } from "../../webapp/publicApi";

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export type BroadcastButtonKind = "url" | "promo_bot" | "promo_webapp" | "webapp_section";
export type BroadcastButtonDraft = {
  id: number;
  kind: BroadcastButtonKind;
  label: string;
  url: string;
  promoCode: string;
  /** Web app screen a ``webapp_section`` button opens. */
  section: string;
  platform?: string;
  app?: string;
  iconCustomEmojiId?: string | null;
  iconEmoji?: string;
  /**
   * Author's own caption per language code. Empty everywhere is the normal
   * case: the button then shows the prepared caption for its kind in the
   * recipient's own language.
   */
  labels?: Record<string, string>;
};
export type BroadcastPromoOption = { value: string; label: string; group?: string };
export const MAX_BROADCAST_BUTTONS = 4;

export function buttonDraftValid(button: BroadcastButtonDraft): boolean {
  // An empty caption is no longer a mistake: the button then shows the
  // prepared caption for its kind in the recipient's own language.
  if (button.label.trim().length > 64) return false;
  if (Object.values(button.labels ?? {}).some((label) => label.trim().length > 64)) return false;
  if (button.kind === "url") {
    return normalizeMessageButtonLink(button.url) !== null;
  }
  if (button.kind === "webapp_section") return Boolean(button.section.trim());
  return /^[A-Za-z0-9_-]{1,58}$/.test(button.promoCode.trim());
}

export function localizedForPayload(
  values: Record<string, string> | undefined
): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const [language, text] of Object.entries(values ?? {})) {
    const body = String(text ?? "").trim();
    // An empty tab means "not written yet"; sending it would deliver an empty
    // caption to exactly the customers who read that language.
    if (body) payload[language.toLowerCase()] = body;
  }
  return payload;
}

/** Drafted buttons as the message contract expects them, shared with support. */
export function buttonsForPayload(buttons: BroadcastButtonDraft[]) {
  return buttons.map((button) => ({
    kind: button.kind,
    label: button.label.trim(),
    labels: localizedForPayload(button.labels),
    url: button.kind === "url" ? normalizeMessageButtonLink(button.url) || button.url.trim() : "",
    promo_code:
      button.kind === "url" || button.kind === "webapp_section" ? "" : button.promoCode.trim(),
    section: button.kind === "webapp_section" ? button.section.trim() : "",
    ...(button.kind === "webapp_section" && button.section.trim() === "install"
      ? {
          ...(button.platform?.trim() ? { platform: button.platform.trim() } : {}),
          ...(button.app?.trim() ? { app: button.app.trim() } : {}),
        }
      : {}),
    icon_custom_emoji_id: button.iconCustomEmojiId || null,
    icon_emoji: button.iconEmoji || "",
  }));
}

type PromoListItem = components["schemas"]["PromoOptionOut"];
type PromosListResponse = GetResponse<"/api/admin/promos/options">;

/**
 * A code minted for one named customer.
 *
 * Ownership is explicit: only ``user_id`` marks a code as personal. A code
 * that merely allows a single activation is still an ordinary shared code and
 * stays in the shared group.
 */
function promoIsPersonal(promo: PromoListItem): boolean {
  return Boolean(promo.user_id);
}

function promoOptionLabel(promo: PromoListItem): string {
  const code = String(promo.code || "");
  const max = Number(promo.max_activations);
  const current = Number(promo.current_activations);
  if (Number.isFinite(max) && max > 0 && Number.isFinite(current)) {
    return `${code} · ${current}/${max}`;
  }
  return code;
}

export function isPromosListResponse(value: unknown): value is PromosListResponse {
  return Boolean(value && typeof value === "object" && (value as { ok?: unknown }).ok === true);
}

export function promoOptionsFromResponse(
  response: PromosListResponse,
  at: TranslateFn
): BroadcastPromoOption[] {
  const sharedGroup = at("broadcast_promo_group_shared", {}, "Shared codes");
  const personalGroup = at("broadcast_promo_group_personal", {}, "Personal codes");
  const options = (response.promos || [])
    .map((promo) => ({
      value: String(promo.code || ""),
      label: promoOptionLabel(promo),
      group: promoIsPersonal(promo) ? personalGroup : sharedGroup,
    }))
    .filter((option) => option.value);
  // Keep ownership visually strict even when the server ranks one exact
  // personal match above similar shared codes: shared is always the first group.
  return [
    ...options.filter((option) => option.group === sharedGroup),
    ...options.filter((option) => option.group === personalGroup),
  ];
}

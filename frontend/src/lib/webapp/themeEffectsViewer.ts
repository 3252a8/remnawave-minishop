import type { UserProfile } from "./types";

type EffectsViewer = Pick<UserProfile, "id" | "is_admin"> | null | undefined;

/** Stable key of the signed-in account; a change restarts a running theme effect. */
export function themeEffectsIdentity(user: EffectsViewer): string {
  return user?.id ? String(user.id) : "";
}

/**
 * Whether the Mini App may run the active theme's JavaScript for this viewer.
 * Signed-in visitors always may; administrators only with an explicit theme
 * preview or the «JavaScript темы для администраторов» appearance setting.
 */
export function themeEffectsEnabled({
  mode,
  screen,
  user,
  previewKey,
  adminEffectsEnabled,
}: {
  mode: string;
  screen: string;
  user: EffectsViewer;
  previewKey: string;
  adminEffectsEnabled: boolean;
}): boolean {
  return (
    mode === "app" &&
    screen !== "admin" &&
    Boolean(themeEffectsIdentity(user)) &&
    (!user?.is_admin || Boolean(previewKey) || adminEffectsEnabled)
  );
}

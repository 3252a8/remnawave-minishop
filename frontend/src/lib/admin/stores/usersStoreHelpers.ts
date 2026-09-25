import { withRoutePrefix } from "../../webapp/routes.js";
import { copyTextToClipboard } from "../../webapp/clipboard.js";
import {
  buildAdminPaymentsPath,
  buildAdminPaymentsUserPath,
  buildAdminUserPath,
  buildAdminUsersPath,
} from "../../webapp/publicApi";
import { closedUserModalState } from "./usersStoreState";
import type { AdminStoreState, AdminSubscription, AdminUser, PathContext } from "./usersStoreState";

export function openingUserModalState(
  user: AdminUser | null,
  userId: number | string
): Partial<AdminStoreState> {
  return {
    ...closedUserModalState(),
    openedUser: user,
    userDetailLoading: true,
    userDetailTab: "subscription",
    userLogsUserId: userId,
  };
}

export function userFromRoute(userOrId: AdminUser | number | string): AdminUser {
  if (typeof userOrId === "object") return userOrId;
  const isMinishopId = typeof userOrId === "string" && userOrId.startsWith("ms_");
  return {
    user_id: isMinishopId ? 0 : Number(userOrId),
    minishop_id: isMinishopId ? String(userOrId) : null,
  };
}

export function isCurrentUserRequest(
  state: AdminStoreState,
  requestId: number,
  userId: number | string,
  currentRequestId: number
): boolean {
  const openedUser = state.openedUser;
  return (
    requestId === currentRequestId &&
    Boolean(openedUser) &&
    (openedUser?.user_id === userId || openedUser?.minishop_id === userId)
  );
}

function gbDraftFromBytes(bytes: unknown) {
  const value = Number(bytes || 0);
  return value > 0 ? +(value / 1024 ** 3).toFixed(2) : "";
}

export function draftStateFromSubscription(sub: AdminSubscription | null | undefined) {
  const bonusGb = gbDraftFromBytes(sub?.premium_bonus_bytes);
  const regularBonusGb = gbDraftFromBytes(sub?.regular_bonus_bytes);
  const hasHwidLimit = sub?.hwid_device_limit !== null && sub?.hwid_device_limit !== undefined;
  const hwidLimit = hasHwidLimit ? Number(sub?.hwid_device_limit) : null;
  const hwidUnlimited = hasHwidLimit && hwidLimit === 0;
  const hwidLimitDraft =
    hasHwidLimit && hwidLimit !== null && hwidLimit > 0 ? String(hwidLimit) : "";
  return {
    tariffKey: String(sub?.tariff_key || ""),
    trafficStrategy: String(sub?.traffic_limit_strategy || "NO_RESET").trim() || "NO_RESET",
    premiumUnlimited: Boolean(sub?.premium_unlimited_override),
    premiumBonusGb: bonusGb,
    regularUnlimited: Boolean(sub?.regular_unlimited_override),
    regularBonusGb,
    hwidUnlimited,
    hwidDeviceLimit: hwidLimitDraft,
  };
}

export function resolvePathContext(active: string, context: PathContext | undefined): PathContext {
  if (context === "payments") return "payments";
  return active === "users" ? "users" : null;
}

export function pushUserPath(
  active: string,
  pathContext: PathContext,
  userId: number | string | null,
  routePrefix: string,
  replace = false
): void {
  if (typeof window === "undefined" || window.location.protocol === "file:") return;
  let target = "";
  if (active === "users") target = userId ? buildAdminUserPath(userId) : buildAdminUsersPath();
  else if (active === "payments" && pathContext === "payments") {
    target = userId ? buildAdminPaymentsUserPath(userId) : buildAdminPaymentsPath();
  }
  if (!target) return;
  target = withRoutePrefix(target, routePrefix);
  if (window.location.pathname !== target) {
    window.history[replace ? "replaceState" : "pushState"](
      null,
      "",
      `${target}${window.location.search}${window.location.hash}`
    );
  }
}

export async function copyText(
  text: string | null | undefined,
  successMessage: string,
  onToast: (message: string) => void,
  copy: (value: string) => Promise<boolean> = copyTextToClipboard
): Promise<void> {
  if (!text) return;
  let copied: boolean;
  try {
    copied = await copy(text);
  } catch {
    copied = false;
  }
  onToast(copied ? successMessage : text);
}

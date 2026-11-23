import {
  buildAdminTariffsPath,
  buildAdminUserActionPath,
  buildAdminUserPath,
  unwrap,
} from "$lib/webapp/publicApi";
import type { AdminApi, AdminUser } from "./usersStoreState";

export type BulkUserAction =
  | { type: "traffic-grant"; kind: "regular" | "premium"; gb: number }
  | { type: "tariff"; tariffKey: string }
  | { type: "extend"; days: number }
  | { type: "traffic-reset" | "subscription-reissue" | "delete" };

export const bulkUserActionLabels = {
  "traffic-grant": "users_bulk_traffic",
  tariff: "users_bulk_tariff",
  extend: "users_bulk_extend",
  "traffic-reset": "users_bulk_reset",
  "subscription-reissue": "users_bulk_reissue",
  delete: "users_bulk_delete",
} satisfies Record<BulkUserAction["type"], string>;

type UserId = AdminUser["user_id"];
export type BulkUserActionResult =
  | { userId: UserId; status: "applied" | "unconfirmed" }
  | { userId: UserId; status: "rejected"; error: unknown };

async function applyUserAction(api: AdminApi, userId: UserId, action: BulkUserAction) {
  if (action.type === "delete") {
    const response = await api(buildAdminUserPath(userId), { method: "DELETE" });
    if (!response?.ok) throw response;
    return Boolean(unwrap(response).ok);
  }

  let payload: object | undefined;
  switch (action.type) {
    case "tariff":
      payload = { tariff_key: action.tariffKey, apply_tariff_hwid_limit: false };
      break;
    case "traffic-grant":
      payload = { kind: action.kind, gb: action.gb };
      break;
    case "extend":
      payload = { days: action.days, extend_hwid_devices: false, keep_tariff: true };
      break;
  }
  const response = await api(buildAdminUserActionPath(userId, action.type), {
    method: "POST",
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response?.ok) throw response;
  const data = unwrap(response);
  if (action.type === "traffic-grant") {
    return "grant" in data && data.grant?.kind === action.kind && data.grant.granted_bytes > 0;
  }
  if (action.type === "tariff") {
    return "subscription" in data && data.subscription?.tariff_key === action.tariffKey;
  }
  return true;
}

async function applyBulkUserAction(
  api: AdminApi,
  action: BulkUserAction,
  userIds: readonly UserId[],
  onResult: (result: BulkUserActionResult) => void
): Promise<void> {
  // Each existing admin action commits independently. Serial requests keep one
  // bulk operation from sending a page of updates to the panel at once.
  for (const userId of new Set(userIds)) {
    let result: BulkUserActionResult;
    try {
      const applied = await applyUserAction(api, userId, action);
      result = { userId, status: applied ? "applied" : "unconfirmed" };
    } catch (error) {
      result =
        error && typeof error === "object" && "ok" in error && error.ok === false
          ? { userId, status: "rejected", error }
          : { userId, status: "unconfirmed" };
    }
    onResult(result);
  }
}

export function createUsersStoreBulkActions(
  api: AdminApi,
  invalidateUser: (userId: UserId) => void,
  refreshUsers: () => Promise<void>
) {
  return {
    async applyBulkAction(
      action: BulkUserAction,
      userIds: readonly UserId[],
      onResult: (result: BulkUserActionResult) => void
    ) {
      await applyBulkUserAction(api, action, userIds, (result) => {
        if (result.status !== "rejected") invalidateUser(result.userId);
        onResult(result);
      });
      await refreshUsers();
    },
    async loadBulkTariffs() {
      const response = await api(buildAdminTariffsPath());
      if (!response?.ok) throw response;
      const data = unwrap(response);
      return (data.catalog?.tariffs ?? []).filter((tariff) => tariff.billing_model === "period");
    },
  };
}

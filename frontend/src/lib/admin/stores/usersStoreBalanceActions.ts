import { adminErrorMessage } from "../errors.js";
import { buildAdminUserActionPath } from "../../webapp/publicApi.js";
import type {
  AdminApi,
  AdminStoreState,
  SnapshotOptions,
  ToastFn,
  TranslateFn,
} from "./usersStoreState.js";

type BalanceAdjustment = {
  target: "user" | "partner";
  mode: "add" | "subtract" | "set";
  amount: number;
  reason: string;
  idempotency_key: string;
};

type BalanceConversion = {
  direction: "partner_to_user" | "user_to_partner";
  amount: number;
  reason: string;
  idempotency_key: string;
};

const preserveOtherDrafts: SnapshotOptions = {
  resetExtendTariff: false,
  resetTariffAction: false,
  resetTrafficStrategy: false,
  resetPremium: false,
  resetRegular: false,
  resetHwid: false,
  resetGrant: false,
  resetSquadOverrides: false,
};

export function createUsersStoreBalanceActions({
  api,
  onToast,
  at,
  readStateSnapshot,
  applyState,
  invalidateUsersQueries,
  refreshOpenedUserDetail,
  reportUserActionError,
}: {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  readStateSnapshot: () => AdminStoreState;
  applyState: (updater: (snapshot: AdminStoreState) => AdminStoreState) => void;
  invalidateUsersQueries: (userId?: number | string) => void;
  refreshOpenedUserDetail: (options?: SnapshotOptions) => Promise<unknown>;
  reportUserActionError: (error: unknown) => void;
}) {
  async function applyBalanceAction(
    action: "balance-adjustment" | "balance-conversion",
    payload: BalanceAdjustment | BalanceConversion,
    successKey: string,
    fallback: string
  ): Promise<boolean> {
    const s = readStateSnapshot();
    if (!s.openedUser) return false;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, action), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res?.ok) {
        onToast(adminErrorMessage(res, at));
        return false;
      }
      invalidateUsersQueries(s.openedUser.user_id);
      onToast(at(successKey, {}, fallback));
      await refreshOpenedUserDetail(preserveOtherDrafts);
      return true;
    } catch (error) {
      reportUserActionError(error);
      return false;
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  return {
    adjustUserBalance: (payload: BalanceAdjustment) =>
      applyBalanceAction(
        "balance-adjustment",
        payload,
        "user_balance_adjustment_saved",
        "Balance updated"
      ),
    convertUserBalance: (payload: BalanceConversion) =>
      applyBalanceAction(
        "balance-conversion",
        payload,
        "user_balance_conversion_saved",
        "Balance converted"
      ),
  };
}

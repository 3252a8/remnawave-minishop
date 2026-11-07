import { adminErrorMessage } from "../errors.js";
import { buildAdminUserActionPath } from "../../webapp/publicApi";
import type {
  AdminStoreState,
  AdminApi,
  SnapshotOptions,
  ToastFn,
  TranslateFn,
} from "./usersStoreState";

export function createUsersStoreHwidResetAction({
  api,
  onToast,
  at,
  readStateSnapshot,
  applyState,
  invalidateUsersQueries,
  refreshOpenedUserDetail,
}: {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  readStateSnapshot: () => AdminStoreState;
  applyState: (updater: (state: AdminStoreState) => AdminStoreState) => void;
  invalidateUsersQueries: (userId?: number | string) => void;
  refreshOpenedUserDetail: (options?: SnapshotOptions) => Promise<unknown>;
}) {
  async function resetHwidDevicesUser(): Promise<boolean> {
    const state = readStateSnapshot();
    if (!state.openedUser || state.userActionBusy) return false;
    const userId = state.openedUser.user_id;
    applyState((current) => ({ ...current, userActionBusy: true }));
    let succeeded = false;
    try {
      const response = await api(buildAdminUserActionPath(userId, "hwid-devices/reset"), {
        method: "POST",
      });
      succeeded = Boolean(response?.ok);
      onToast(
        succeeded
          ? at("user_hwid_reset_success", {}, "Recorded devices cleared")
          : adminErrorMessage(response, at)
      );
    } catch (error) {
      onToast(
        adminErrorMessage(
          error,
          at,
          at(
            "user_hwid_reset_failed",
            {},
            "Could not clear all recorded devices. Some may already be cleared. Refresh and try again."
          )
        )
      );
    } finally {
      // A failed panel request may still have cleared some devices. Refresh the
      // count, but preserve unsaved limit and subscription drafts.
      invalidateUsersQueries(userId);
      try {
        if (readStateSnapshot().openedUser?.user_id === userId) {
          await refreshOpenedUserDetail({
            resetExtendTariff: false,
            resetTariffAction: false,
            resetTrafficStrategy: false,
            resetPremium: false,
            resetRegular: false,
            resetHwid: false,
            resetGrant: false,
            resetSquadOverrides: false,
          });
        }
      } finally {
        applyState((current) => ({ ...current, userActionBusy: false }));
      }
    }
    return succeeded;
  }

  return { resetHwidDevicesUser };
}

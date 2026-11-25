import { adminErrorMessage } from "../errors.js";
import { buildAdminUserActionPath, unwrap } from "../../webapp/publicApi";
import { buildAdminUserSubscriptionSuspensionPath } from "../../webapp/adminUserPanelPaths";
import type {
  AdminStoreState,
  AdminApi,
  SnapshotOptions,
  ToastFn,
  TranslateFn,
} from "./usersStoreState";

type ApplyState = (updater: (snapshot: AdminStoreState) => AdminStoreState) => void;
type ReadStateSnapshot = () => AdminStoreState;
type InvalidateUsersQueries = (userId?: number | string) => void;
type RefreshOpenedUserDetail = (options?: SnapshotOptions) => Promise<unknown>;

const preserveSubscriptionDrafts: SnapshotOptions = {
  resetExtendTariff: false,
  resetTariffAction: false,
  resetTrafficStrategy: false,
  resetPremium: false,
  resetRegular: false,
  resetHwid: false,
  resetGrant: false,
};

export function createUsersStoreSubscriptionActions({
  api,
  onToast,
  at,
  readStateSnapshot,
  applyState,
  invalidateUsersQueries,
  refreshOpenedUserDetail,
  refreshUsersList,
}: {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  readStateSnapshot: ReadStateSnapshot;
  applyState: ApplyState;
  invalidateUsersQueries: InvalidateUsersQueries;
  refreshOpenedUserDetail: RefreshOpenedUserDetail;
  refreshUsersList: () => Promise<void> | undefined;
}) {
  async function reissueSubscriptionUser() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(
        buildAdminUserActionPath(s.openedUser.user_id, "subscription-reissue"),
        {
          method: "POST",
        }
      );
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        onToast(
          "email_sent" in res && res.email_sent
            ? at(
                "user_subscription_reissued_email",
                {},
                "Subscription link reissued. The new link was emailed to the user"
              )
            : at("user_subscription_reissued", {}, "Subscription link reissued")
        );
        await refreshOpenedUserDetail(preserveSubscriptionDrafts);
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({
        ...st,
        userActionBusy: false,
        userSubscriptionReissueOpen: false,
      }));
    }
  }

  async function setSubscriptionSuspension(
    userId: number | string,
    subscriptionId: number,
    suspended: boolean
  ) {
    const { openedUser, userActionBusy } = readStateSnapshot();
    if (openedUser?.user_id !== userId || userActionBusy) return false;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserSubscriptionSuspensionPath(userId), {
        method: "POST",
        body: JSON.stringify({ subscription_id: subscriptionId, suspended }),
      });
      if (!res?.ok) throw res;
      const { subscription } = unwrap(res);
      invalidateUsersQueries(userId);
      if (openedUser.minishop_id) invalidateUsersQueries(openedUser.minishop_id);
      applyState((st) => {
        const detail = st.openedUserDetail;
        if (!detail || detail.user.user_id !== userId) return st;
        return {
          ...st,
          openedUserDetail: {
            ...detail,
            active_subscription: suspended ? null : subscription,
            suspended_subscription: suspended ? subscription : null,
            subscriptions: detail.subscriptions.map((sub) =>
              sub.subscription_id === subscriptionId ? subscription : sub
            ),
          },
        };
      });
      if (readStateSnapshot().openedUser?.user_id === userId) {
        await refreshOpenedUserDetail();
        onToast(at(suspended ? "user_subscription_suspended" : "user_subscription_resumed"));
      }
      await refreshUsersList();
      return true;
    } catch (error) {
      if (readStateSnapshot().openedUser?.user_id === userId) {
        await refreshOpenedUserDetail({
          ...preserveSubscriptionDrafts,
          resetSquadOverrides: false,
        });
      }
      throw error;
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  return { reissueSubscriptionUser, setSubscriptionSuspension };
}

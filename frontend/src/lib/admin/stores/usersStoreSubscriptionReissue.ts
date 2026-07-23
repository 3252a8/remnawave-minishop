import { adminErrorMessage } from "../errors.js";
import { buildAdminUserActionPath } from "../../webapp/publicApi";
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

export function createUsersStoreSubscriptionReissueAction({
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
  readStateSnapshot: ReadStateSnapshot;
  applyState: ApplyState;
  invalidateUsersQueries: InvalidateUsersQueries;
  refreshOpenedUserDetail: RefreshOpenedUserDetail;
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
        await refreshOpenedUserDetail({
          resetExtendTariff: false,
          resetTariffAction: false,
          resetTrafficStrategy: false,
          resetPremium: false,
          resetRegular: false,
          resetHwid: false,
          resetGrant: false,
        });
      } else onToast(adminErrorMessage(res, at));
    } finally {
      applyState((st) => ({
        ...st,
        userActionBusy: false,
        userSubscriptionReissueOpen: false,
      }));
    }
  }

  return { reissueSubscriptionUser };
}

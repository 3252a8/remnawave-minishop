import { adminErrorMessage } from "../errors.js";
import type { NotificationPreferences } from "../../webapp/notificationPreferences.js";
import { buildAdminUserActionPath } from "../../webapp/publicApi.js";
import type { AdminApi, AdminStoreState, ToastFn, TranslateFn } from "./usersStoreState.js";

type ApplyState = (updater: (snapshot: AdminStoreState) => AdminStoreState) => void;

export function createUsersStoreNotificationPreferenceActions({
  api,
  onToast,
  at,
  readStateSnapshot,
  applyState,
  invalidateUsersQueries,
}: {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  readStateSnapshot: () => AdminStoreState;
  applyState: ApplyState;
  invalidateUsersQueries: (userId?: number | string) => void;
}) {
  async function updateUserNotificationPreferences(
    preferences: NotificationPreferences
  ): Promise<void> {
    const snapshot = readStateSnapshot();
    if (!snapshot.openedUser || snapshot.userActionBusy) return;
    applyState((state) => ({ ...state, userActionBusy: true }));
    try {
      const response = await api(
        buildAdminUserActionPath(snapshot.openedUser.user_id, "notification-preferences"),
        { method: "PATCH", body: JSON.stringify(preferences) }
      );
      if (!response?.ok) {
        onToast(adminErrorMessage(response, at));
        return;
      }
      const responsePreferences = (
        response as unknown as { notification_preferences: NotificationPreferences }
      ).notification_preferences;
      invalidateUsersQueries(snapshot.openedUser.user_id);
      applyState((state) =>
        state.openedUserDetail
          ? {
              ...state,
              openedUserDetail: {
                ...state.openedUserDetail,
                notification_preferences: responsePreferences,
              },
            }
          : state
      );
      onToast(at("user_notifications_saved", {}, "Notification preferences saved"));
    } finally {
      applyState((state) => ({ ...state, userActionBusy: false }));
    }
  }

  return { updateUserNotificationPreferences };
}

import { adminErrorMessage } from "../errors.js";
import { buildAdminUserActionPath } from "../../webapp/publicApi";
import type {
  AdminPanelSquadOverrides,
  AdminStoreState,
  AdminApi,
  ToastFn,
  TranslateFn,
} from "./usersStoreState";

type ApplyState = (updater: (snapshot: AdminStoreState) => AdminStoreState) => void;
type ReadStateSnapshot = () => AdminStoreState;
type InvalidateUsersQueries = (userId?: number | string) => void;

function panelSquadOverridesFromResponse(response: unknown): AdminPanelSquadOverrides | null {
  if (!response || typeof response !== "object") return null;
  const payload = response as { panel_squad_overrides?: AdminPanelSquadOverrides | null };
  return payload.panel_squad_overrides || null;
}

export function applySquadOverridesSnapshot(
  s: AdminStoreState,
  panelSquadOverrides: AdminPanelSquadOverrides | null | undefined
): AdminStoreState {
  if (!s.openedUserDetail || !panelSquadOverrides) return s;
  const external = panelSquadOverrides.external || null;
  const mode = String(external?.mode || "inherit");
  return {
    ...s,
    openedUserDetail: {
      ...s.openedUserDetail,
      panel_squad_overrides: panelSquadOverrides,
    },
    userSquadOverrideDraft: "",
    userExternalSquadModeDraft: mode === "set" || mode === "cleared" ? mode : "inherit",
    userExternalSquadUuidDraft: String(
      external?.manual_uuid || (mode === "set" ? external?.effective_uuid || "" : "") || ""
    ),
  };
}

export function createUsersStoreSquadOverrideActions({
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
  readStateSnapshot: ReadStateSnapshot;
  applyState: ApplyState;
  invalidateUsersQueries: InvalidateUsersQueries;
}) {
  async function applySquadOverridesPatch(body: Record<string, unknown>, successMessage: string) {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(buildAdminUserActionPath(s.openedUser.user_id, "squad-overrides"), {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        const panelSquadOverrides = panelSquadOverridesFromResponse(res);
        applyState((st) => applySquadOverridesSnapshot(st, panelSquadOverrides));
        onToast(successMessage);
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function refreshUserSquadOverrides() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    applyState((st) => ({ ...st, userActionBusy: true }));
    try {
      const res = await api(
        buildAdminUserActionPath(s.openedUser.user_id, "squad-overrides/refresh"),
        { method: "POST" }
      );
      if (res?.ok) {
        invalidateUsersQueries(s.openedUser.user_id);
        const panelSquadOverrides = panelSquadOverridesFromResponse(res);
        applyState((st) => applySquadOverridesSnapshot(st, panelSquadOverrides));
        onToast(at("user_squad_overrides_refreshed", {}, "Squads refreshed from panel"));
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      applyState((st) => ({ ...st, userActionBusy: false }));
    }
  }

  async function addUserInternalSquadOverride() {
    const s = readStateSnapshot();
    const squadUuid = String(s.userSquadOverrideDraft || "").trim();
    if (!s.openedUser || !squadUuid) return;
    await applySquadOverridesPatch(
      { add_internal_squad_uuids: [squadUuid], sync_panel: true },
      at("user_squad_override_added", {}, "Internal squad added")
    );
  }

  async function removeUserInternalSquadOverride(squadUuid: string) {
    const s = readStateSnapshot();
    const cleaned = String(squadUuid || "").trim();
    if (!s.openedUser || !cleaned) return;
    await applySquadOverridesPatch(
      { remove_internal_squad_uuids: [cleaned], sync_panel: true },
      at("user_squad_override_removed", {}, "Internal squad removed")
    );
  }

  async function saveUserExternalSquadOverride() {
    const s = readStateSnapshot();
    if (!s.openedUser) return;
    const mode = s.userExternalSquadModeDraft || "inherit";
    const externalUuid = String(s.userExternalSquadUuidDraft || "").trim();
    if (mode === "set" && !externalUuid) {
      onToast(at("user_external_squad_uuid_required", {}, "Enter an external squad UUID"));
      return;
    }
    await applySquadOverridesPatch(
      {
        external_mode: mode,
        external_squad_uuid: mode === "set" ? externalUuid : null,
        sync_panel: true,
      },
      at("user_external_squad_saved", {}, "External squad saved")
    );
  }

  return {
    refreshUserSquadOverrides,
    addUserInternalSquadOverride,
    removeUserInternalSquadOverride,
    saveUserExternalSquadOverride,
  };
}

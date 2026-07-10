import type { AdminUser } from "$lib/admin/stores/usersStore";
import type { AdminUserDetail, TranslateFn } from "$lib/admin/stores/usersStoreState";

export type { TranslateFn };

export type SelectOption = { value: string; label: string };
export type MoneyFormatter = (value: unknown, currency?: string | null) => string;
export type DateFormatter = (value: unknown) => string;
export type BadgeVariant = "success" | "danger" | "warning" | "muted";
export type UserLogRow = Record<string, unknown> & { log_id?: number | string };
export type ActiveSubscription = NonNullable<AdminUserDetail["active_subscription"]>;

export type UsersStoreBridge = {
  userDetailTab: string;
  copyToClipboard: (value: string | null | undefined, message?: string) => void;
  openUserReferrals: (page?: number) => void | Promise<void>;
  addUserInternalSquadOverride: () => void | Promise<void>;
  removeUserInternalSquadOverride: (squadUuid: string) => void | Promise<void>;
  refreshUserSquadOverrides: () => void | Promise<void>;
  saveUserExternalSquadOverride: () => void | Promise<void>;
};

export type RelatedUserOpener = (user: AdminUser | null | undefined) => void;

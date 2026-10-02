import { withDemoIdentities } from "../demoIdentities.js";
import { DEMO_DATASET } from "../demoDataset.js";
import { structuredCloneSafe } from "../../safeClone.js";

export type DemoRecord = Record<string, unknown>;

export type DemoAdminUser = DemoRecord & {
  id?: number | string | null;
  user_id?: number | string | null;
  minishop_id?: string | null;
  telegram_id?: number | string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  panel_user_uuid?: string | null;
  is_banned?: boolean | null;
  telegram_linked?: boolean | null;
  panel_status?: string | null;
  registration_date?: string | null;
  referred_by_id?: number | string | null;
  premium_traffic?: (DemoRecord & { state?: string | null; percent?: number | null }) | null;
  payments_count?: number | null;
  payments_total_amount?: number | null;
  payments_currency?: string | null;
  invited_users_count?: number | null;
  subscription_expires_at?: string | null;
  panel_status_expired_at?: string | null;
};

export type DemoTicket = DemoRecord & {
  ticket_id?: number;
  user_id?: number | string | null;
  subject?: string | null;
  category?: string | null;
  priority?: string | null;
  status?: string | null;
  unread_user_count?: number | null;
  unread_admin_count?: number | null;
  last_message_at?: string | null;
  created_at?: string | null;
  user?: DemoAdminUser | null;
};

export type DemoUserDetail = DemoRecord & {
  user?: DemoAdminUser;
  active_subscription?: DemoRecord;
  referral?: DemoRecord & { inviter?: DemoAdminUser | null };
};

export type DemoSettingsField = DemoRecord & { key: string };

// The generated dataset is consumed as a loose record: the mock probes optional
// fields that older snapshots may not carry.
export type DemoDataset = DemoRecord & {
  stats?: DemoRecord;
  promos?: DemoRecord[];
  ads?: DemoRecord[];
  adsTotals?: DemoRecord;
  adminPayments?: DemoRecord[];
  adminLogs?: (DemoRecord & { user_id?: unknown; target_user_id?: unknown })[];
  adminUsers?: DemoAdminUser[];
  adminUserDetails?: Record<string, DemoUserDetail>;
  supportTickets?: DemoTicket[];
  supportMessages?: Record<string, DemoRecord[]>;
  tariffsCatalog?: DemoRecord;
  panelSquads?: DemoRecord[];
  settingsSections?: (DemoRecord & { fields?: DemoSettingsField[] })[];
  translations?: DemoRecord & { groups?: DemoRecord[]; languages?: DemoRecord[] };
  backups?: DemoRecord & { archives?: (DemoRecord & { name?: string })[] };
  currentUser?: DemoAdminUser | null;
  currentSubscription?: DemoRecord | null;
  plans?: DemoRecord[];
  paymentMethods?: DemoRecord[];
  referral?: DemoRecord;
  webappSettings?: DemoRecord;
  tariff_change_options?: DemoRecord;
  topup_options?: DemoRecord;
  device_topup_options?: DemoRecord;
};

export const DATASET = withDemoIdentities(DEMO_DATASET) as unknown as DemoDataset;

export function defaultClone<T>(value: T): T {
  return structuredCloneSafe(value);
}

export type CloneFn = <T>(value: T) => T;

export type MockApiContext = Record<string, unknown> & {
  currentLang?: string;
  normalizeLangCode?: (value: unknown) => string;
  clone?: CloneFn;
};

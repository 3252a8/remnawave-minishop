import {
  buildAdminUsersPath,
  builtApiPath,
  unwrap,
  type ApiClient,
} from "$lib/webapp/publicApi.js";
import type { AdminUserDetail, AdminUsersListResponse } from "./stores/usersStoreState.js";
import { USERS_PAGE_SIZE } from "./stores/usersStoreState.js";

export async function fetchMergeCandidates(api: ApiClient["api"], query: string, page: number) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(USERS_PAGE_SIZE),
    filter: "all",
    sort: "created_desc",
  });
  if (query.trim()) params.set("q", query.trim());
  return unwrap(await api(buildAdminUsersPath(params))) as AdminUsersListResponse;
}

export async function fetchMergeUser(api: ApiClient["api"], id: string): Promise<AdminUserDetail> {
  return unwrap(
    await api(
      builtApiPath<"/api/admin/users/{user_id}">(`/admin/users/${encodeURIComponent(id.trim())}`)
    )
  ) as AdminUserDetail;
}

export async function fetchMergeContext(api: ApiClient["api"], id: number) {
  return unwrap(
    await api(
      builtApiPath<"/api/admin/users/{user_id}/merge-context">(`/admin/users/${id}/merge-context`),
      { cache: "no-store" }
    )
  );
}
export type UserMergeContext = Awaited<ReturnType<typeof fetchMergeContext>>;

export async function mergeUsers(
  api: ApiClient["api"],
  target: number,
  source: number,
  confirmation: number
) {
  return unwrap(
    await api(builtApiPath<"/api/admin/users/{user_id}/merge">(`/admin/users/${target}/merge`), {
      method: "POST",
      body: JSON.stringify({ source_user_id: source, confirmation_user_id: confirmation }),
    })
  );
}

export function mergeErrorKey(error: unknown): string {
  const payload =
    error && typeof error === "object"
      ? (error as { error?: unknown; payload?: { error?: unknown } })
      : {};
  const code = String(payload.error || payload.payload?.error || "");
  const keys: Record<string, string> = {
    account_merge_not_required: "user_merge_same_user",
    account_merge_confirmation_required: "user_merge_confirmation_invalid",
    account_merge_privileged_source: "user_merge_protected",
    account_merge_current_admin: "user_merge_current_admin",
    account_merge_banned: "user_merge_banned",
    account_merge_telegram_conflict: "user_merge_telegram_conflict",
    account_merge_duplicate_promo_conflict: "user_merge_promo_conflict",
    account_merge_google_conflict: "user_merge_provider_conflict",
    account_merge_yandex_conflict: "user_merge_provider_conflict",
    account_merge_provider_conflict: "user_merge_provider_conflict",
    account_merge_recurring_cancel_failed: "user_merge_recurring_conflict",
    account_merge_conflict: "user_merge_conflict",
    not_found: "user_merge_not_found",
    forbidden: "user_merge_forbidden",
  };
  return keys[code] || "user_merge_failed";
}

/** These errors require a fresh review of the pair before another destructive request. */
export function mergeErrorBlocksRetry(error: unknown): boolean {
  return [
    "user_merge_same_user",
    "user_merge_protected",
    "user_merge_current_admin",
    "user_merge_banned",
    "user_merge_telegram_conflict",
    "user_merge_promo_conflict",
    "user_merge_provider_conflict",
    "user_merge_recurring_conflict",
    "user_merge_conflict",
    "user_merge_forbidden",
  ].includes(mergeErrorKey(error));
}

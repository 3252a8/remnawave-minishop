import { describe, expect, it } from "vitest";
import { createApiClient } from "$lib/webapp/publicApi";
import {
  fetchMergeCandidates,
  fetchMergeContext,
  mergeErrorBlocksRetry,
  mergeErrorKey,
  mergeUsers,
} from "./userMergeApi";

describe("manual merge API", () => {
  it("uses the main user list search and fetches fresh credential metadata", async () => {
    const paths: string[] = [];
    const client = createApiClient({
      mockApi: async (path, options) => {
        paths.push(path);
        if (path.endsWith("/merge-context")) {
          expect(options?.cache).toBe("no-store");
          return {
            ok: true,
            user_id: 123,
            auth_identities: [],
            verified_emails: [],
            passkey_count: 0,
            password_available: true,
            merge_eligibility: { allowed: true, reason: null },
          };
        }
        return { ok: true, users: [], total: 0, page: 1, page_size: 25 };
      },
    });
    await fetchMergeCandidates(client.api, " @alice ", 1);
    await fetchMergeContext(client.api, 123);
    expect(paths).toEqual([
      "/admin/users?page=1&page_size=25&filter=all&sort=created_desc&q=%40alice",
      "/admin/users/123/merge-context",
    ]);
  });
  it("keeps target direction and numeric negative source IDs", async () => {
    let request: RequestInit | undefined;
    const client = createApiClient({
      mockApi: async (path, options) => {
        expect(path).toBe("/admin/users/123/merge");
        request = options;
        return {
          ok: true,
          user_id: 123,
          source_user_id: -44,
          panel_reconciliation_pending: false,
          final_end_date: null,
        };
      },
    });
    await mergeUsers(client.api, 123, -44, 123);
    expect(JSON.parse(String(request?.body))).toEqual({
      source_user_id: -44,
      confirmation_user_id: 123,
    });
  });
  it("maps known conflicts to localized copy instead of backend details", () => {
    expect(
      mergeErrorKey({ error: "account_merge_privileged_source", detail: "private details" })
    ).toBe("user_merge_protected");
    expect(mergeErrorKey({ payload: { error: "account_merge_telegram_conflict" } })).toBe(
      "user_merge_telegram_conflict"
    );
    expect(mergeErrorKey({ error: "unexpected" })).toBe("user_merge_failed");
    // Older servers may still return the retired shared-code restriction.
    expect(mergeErrorKey({ error: "account_merge_duplicate_promo_conflict" })).toBe(
      "user_merge_promo_conflict"
    );
  });
  it("requires fresh review after business conflicts but allows transient retry", () => {
    for (const error of [
      "account_merge_privileged_source",
      "account_merge_current_admin",
      "account_merge_banned",
      "account_merge_telegram_conflict",
      "account_merge_duplicate_promo_conflict",
      "account_merge_google_conflict",
      "account_merge_yandex_conflict",
      "account_merge_provider_conflict",
      "account_merge_recurring_cancel_failed",
      "account_merge_conflict",
      "forbidden",
    ])
      expect(mergeErrorBlocksRetry({ payload: { error } })).toBe(true);
    for (const cause of [
      new TypeError("Failed to fetch"),
      { status: 500, error: "account_merge_failed" },
      { error: "account_merge_confirmation_required" },
    ])
      expect(mergeErrorBlocksRetry(cause)).toBe(false);
  });
});

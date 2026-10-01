import { describe, expect, it } from "vitest";

import type { UserProfile } from "./types";
import { themeEffectsEnabled, themeEffectsIdentity } from "./themeEffectsViewer";

// Shaped like the `user` object of /api/me: the account id is `id`, there is no `user_id`.
const visitor = { id: 42, is_admin: false } satisfies Pick<UserProfile, "id" | "is_admin">;
const admin = { id: 7, is_admin: true } satisfies Pick<UserProfile, "id" | "is_admin">;
const storefront = { mode: "app", screen: "home", previewKey: "", adminEffectsEnabled: false };

describe("theme effects viewer", () => {
  it("runs effects for a signed-in visitor as /api/me returns it", () => {
    expect(themeEffectsEnabled({ ...storefront, user: visitor })).toBe(true);
    expect(themeEffectsIdentity(visitor)).toBe("42");
  });

  it("needs a signed-in account", () => {
    expect(themeEffectsEnabled({ ...storefront, user: null })).toBe(false);
    expect(themeEffectsIdentity(undefined)).toBe("");
  });

  it("stays off while loading and on the admin screen", () => {
    expect(themeEffectsEnabled({ ...storefront, mode: "loading", user: visitor })).toBe(false);
    expect(themeEffectsEnabled({ ...storefront, screen: "admin", user: visitor })).toBe(false);
  });

  it("runs for administrators only with a preview or the appearance setting", () => {
    expect(themeEffectsEnabled({ ...storefront, user: admin })).toBe(false);
    expect(themeEffectsEnabled({ ...storefront, user: admin, previewKey: "sample" })).toBe(true);
    expect(themeEffectsEnabled({ ...storefront, user: admin, adminEffectsEnabled: true })).toBe(
      true
    );
  });
});

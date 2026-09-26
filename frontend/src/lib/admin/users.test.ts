import { describe, expect, it, vi } from "vitest";

import {
  createGravatarCache,
  userAvatarUrl,
  userDisplayName,
  userInitials,
  userSecondaryName,
  userTelegramProfileLink,
  userTelegramProfileLinkKind,
} from "./users.js";

describe("admin user helpers", () => {
  it("builds display names and initials from the strongest available identity", () => {
    expect(userDisplayName({ first_name: "Ann", last_name: "Lee", username: "ann" })).toBe(
      "Ann Lee"
    );
    expect(userSecondaryName({ first_name: "Ann", last_name: "Lee", username: "ann" })).toBe(
      "@ann"
    );
    expect(userInitials({ first_name: "Ann", last_name: "Lee" })).toBe("AL");
    expect(userInitials({ username: "ann" })).toBe("AN");
    expect(userDisplayName({ user_id: 42, minishop_id: "ms_abc" })).toBe("User ms_abc");
    expect(userDisplayName({ user_id: 42 })).toBe("User —");
    expect(userSecondaryName({ user_id: 42, minishop_id: "ms_abc" })).toBe("");
  });

  it("resolves avatar URLs without using local avatar proxy placeholders", () => {
    expect(userAvatarUrl({ avatar_url: "https://cdn.example/avatar.jpg" })).toBe(
      "https://cdn.example/avatar.jpg"
    );
    expect(userAvatarUrl({ telegram_photo_url: "/api/account/avatar/1" })).toBe("");
    expect(userAvatarUrl({ telegram_photo_url: "https://t.me/i/userpic.jpg" })).toBe(
      "https://t.me/i/userpic.jpg"
    );
  });

  it("prefers username links and falls back to Telegram id deep links", () => {
    expect(userTelegramProfileLink({ username: "@ann lee" })).toBe("https://t.me/ann%20lee");
    expect(userTelegramProfileLinkKind({ username: "ann" })).toBe("username");
    expect(userTelegramProfileLink({ telegram_id: "123.9" })).toBe("tg://user?id=123");
    expect(userTelegramProfileLinkKind({ telegram_id: 123 })).toBe("id");
    expect(userTelegramProfileLink({})).toBe("");
  });

  it("caches generated avatars and batches list refreshes", async () => {
    const scheduled: Array<() => void> = [];
    const onResolved = vi.fn();
    const cache = createGravatarCache(onResolved, (callback) => scheduled.push(callback));

    expect(cache.gravatarUrl(" First@Example.test ")).toBe("");
    expect(cache.gravatarUrl("second@example.test")).toBe("");

    await vi.waitFor(() => expect(scheduled).toHaveLength(1));
    expect(onResolved).not.toHaveBeenCalled();
    scheduled[0]();

    expect(onResolved).toHaveBeenCalledTimes(1);
    expect(cache.gravatarUrl("first@example.test")).toMatch(
      /^https:\/\/gravatar\.com\/avatar\/[a-f0-9]{64}\?d=identicon&s=80$/
    );
    expect(cache.gravatarUrl("SECOND@example.test")).toMatch(
      /^https:\/\/gravatar\.com\/avatar\/[a-f0-9]{64}\?d=identicon&s=80$/
    );
  });
});

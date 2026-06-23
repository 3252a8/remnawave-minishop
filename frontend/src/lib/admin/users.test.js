import { describe, expect, it } from "vitest";

import {
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
    expect(userDisplayName({ user_id: 42 })).toBe("User #42");
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
});

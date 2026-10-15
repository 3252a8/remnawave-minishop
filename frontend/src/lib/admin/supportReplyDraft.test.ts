import { describe, expect, it } from "vitest";
import type { AdminSupportReplyButton } from "../../admin/sections/extensionTypes";
import {
  supportReplyButtonsFromDescriptors,
  supportReplyTextForInsertion,
} from "./supportReplyDraft";

const link: AdminSupportReplyButton = {
  kind: "url",
  label: "Open guide",
  url: "https://example.test/guide",
  promo_code: "",
  section: "",
  labels: { ru: "Открыть инструкцию" },
  icon_custom_emoji_id: "1234567890",
  icon_emoji: "📖",
};

describe("support reply button insertion", () => {
  it("rejects over-limit complete drafts before composer state can change", () => {
    expect(supportReplyTextForInsertion("a".repeat(4001), 4000)).toBeNull();
    expect(supportReplyTextForInsertion("🙂".repeat(4001), 4000)).toBeNull();
    expect(supportReplyTextForInsertion("🙂".repeat(4000), 4000)).toBe("🙂".repeat(4000));
  });

  it("preserves legacy text-only truncation without splitting Unicode characters", () => {
    const text = "🙂".repeat(3999) + "✅end";
    expect(supportReplyTextForInsertion(text, 4000, true)).toBe("🙂".repeat(3999) + "✅");
  });
  it("maps standard wire descriptors into independently editable composer buttons", () => {
    const input: AdminSupportReplyButton[] = [
      link,
      {
        ...link,
        kind: "webapp_section",
        section: "install",
        platform: "ios",
        app: "client-v2",
        url: "",
      },
      { ...link, kind: "promo_bot", promo_code: " CODE ", url: "" },
      { ...link, kind: "promo_webapp", promo_code: " CODE ", url: "" },
    ];
    const result = supportReplyButtonsFromDescriptors(input);
    expect(result?.map((button) => button.kind)).toEqual([
      "url",
      "webapp_section",
      "promo_bot",
      "promo_webapp",
    ]);
    expect(result?.[0]).toMatchObject({
      url: link.url,
      labels: link.labels,
      iconCustomEmojiId: "1234567890",
      iconEmoji: "📖",
    });
    expect(result?.[2].promoCode).toBe("CODE");
    expect(result?.[1]).toMatchObject({ platform: "ios", app: "client-v2" });
    expect(result?.[0].labels).not.toBe(link.labels);
    expect(new Set(result?.map((button) => button.id)).size).toBe(4);
  });

  it("rejects the whole set for an invalid target or more than four buttons", () => {
    expect(
      supportReplyButtonsFromDescriptors([link, { ...link, url: "javascript:alert(1)" }])
    ).toBeNull();
    expect(
      supportReplyButtonsFromDescriptors([{ ...link, kind: "webapp_section", section: "" }])
    ).toBeNull();
    expect(
      supportReplyButtonsFromDescriptors([{ ...link, kind: "promo_bot", promo_code: " " }])
    ).toBeNull();
    expect(supportReplyButtonsFromDescriptors(Array.from({ length: 5 }, () => link))).toBeNull();
    expect(link.url).toBe("https://example.test/guide");
  });

  it("supports explicitly clearing buttons and canonicalizes Telegram link shortcuts", () => {
    expect(supportReplyButtonsFromDescriptors([])).toEqual([]);
    expect(supportReplyButtonsFromDescriptors([{ ...link, url: "@example_bot" }])?.[0].url).toBe(
      "https://t.me/example_bot"
    );
  });
});

import { describe, expect, it } from "vitest";

import { countryFlagParts } from "./countryFlags";

describe("countryFlagParts", () => {
  it("isolates country flags without changing the server name", () => {
    const name = "Primary 🇳🇱 / 🇫🇮 backup";

    const parts = countryFlagParts(name);

    expect(parts).toEqual([
      { kind: "text", value: "Primary " },
      { kind: "flag", value: "🇳🇱" },
      { kind: "text", value: " / " },
      { kind: "flag", value: "🇫🇮" },
      { kind: "text", value: " backup" },
    ]);
    expect(parts.map((part) => part.value).join("")).toBe(name);
  });

  it("keeps names without flags untouched", () => {
    expect(countryFlagParts("NL Amsterdam #1")).toEqual([
      { kind: "text", value: "NL Amsterdam #1" },
    ]);
  });

  it("recognizes subdivision flag tag sequences", () => {
    const england = "🏴\u{e0067}\u{e0062}\u{e0065}\u{e006e}\u{e0067}\u{e007f}";

    expect(countryFlagParts(`${england} London`)).toEqual([
      { kind: "flag", value: england },
      { kind: "text", value: " London" },
    ]);
  });
});

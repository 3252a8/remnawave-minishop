import { describe, expect, it } from "vitest";
import { composeUi, matchesDeviceType, selectExtensionTab } from "./composition";

describe("UI composition v1", () => {
  it("resolves device replacements independently for each device type", () => {
    const entries = [
      {
        id: "routers:card",
        target: "user.devices.card",
        placement: "replace",
        device_types: ["router"],
      },
      {
        id: "phones:card",
        target: "user.devices.card",
        placement: "replace",
        device_types: ["phone"],
      },
    ];
    for (const [index, device_type] of ["router", "phone"].entries()) {
      const result = composeUi(
        entries.filter((entry) => matchesDeviceType(entry, { device: { device_type } })),
        "user.devices.card"
      );
      expect(result.conflict).toBe(false);
      expect(result.replacement).toBe(entries[index]);
    }
    expect(matchesDeviceType(entries[0], {})).toBe(false);
    expect(matchesDeviceType({ device_types: ["unknown"] }, { device: {} })).toBe(true);
  });

  it("keeps both owners, zero order and stable ordering independently of package order", () => {
    const entries = [
      { id: "two:card", target: "user.invite.cards", order: 0 },
      { id: "one:card", target: "user.invite.cards", order: 0 },
      { id: "else:card", target: "user.support.cards", order: -1 },
    ];
    const result = composeUi(entries, "user.invite.cards");
    expect(result.after.map((item) => item.id)).toEqual(["one:card", "two:card"]);
    expect(composeUi(entries.reverse(), "user.invite.cards")).toEqual(result);
  });

  it("retains additive cards but restores Core when replacements conflict", () => {
    const entries = [
      { id: "one:replace", target: "admin.support.content", placement: "replace" },
      { id: "two:replace", target: "admin.support.content", placement: "replace" },
      { id: "two:card", target: "admin.support.content", placement: "before" },
    ];
    expect(composeUi(entries, "admin.support.content")).toMatchObject({
      conflict: true,
      replacement: null,
      before: [entries[2]],
    });
    expect(composeUi(entries.slice(1), "admin.support.content").replacement).toBe(entries[1]);
    expect(composeUi([], "admin.support.content").replacement).toBeNull();
  });

  it("restores direct subsection links and falls back after removal", () => {
    expect(
      selectExtensionTab([{ id: "one:resources" }], "?filter=open&extensionTab=one%3Aresources")
    ).toBe("one:resources");
    expect(selectExtensionTab([], "?extensionTab=one%3Aresources")).toBe("");
  });
});

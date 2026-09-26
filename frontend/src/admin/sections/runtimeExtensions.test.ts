import { afterEach, describe, expect, it, vi } from "vitest";
import { registerRuntimeExtensions } from "./runtimeExtensions";
import { ADMIN_UI_SLOTS, ADMIN_SECTION_TABS } from "./extensionRegistry";
import { ADMIN_SECTIONS, resolveAdminSectionId } from "./registry";

afterEach(() => {
  registerRuntimeExtensions([]);
  vi.unstubAllGlobals();
});
const plugin = (id: string) => ({
  id,
  digest: "a".repeat(64),
  entry: `/api/admin/plugins/assets/${id}/${"a".repeat(64)}/index.js`,
});

describe("runtime UI registrations", () => {
  it("registers tab-only packages and keeps identical local ids from separate owners", () => {
    registerRuntimeExtensions(
      ["sample", "second"].map((id) => ({
        ...plugin(id),
        section_tabs: [{ id: "resources", view: "resources", sectionId: "support", order: 0 }],
        slots: [{ id: "resources", view: "resources", target: "admin.support.content" }],
      }))
    );
    expect(
      ADMIN_SECTION_TABS.filter((tab) => tab.sectionId === "support").map((tab) => tab.id)
    ).toEqual(["sample:resources", "second:resources"]);
    expect(ADMIN_SECTION_TABS.find((tab) => tab.id === "sample:resources")?.order).toBe(0);
    expect(ADMIN_UI_SLOTS).toHaveLength(2);
    registerRuntimeExtensions([]);
    expect(ADMIN_UI_SLOTS).toHaveLength(0);
    expect(ADMIN_SECTION_TABS.some((tab) => tab.id === "sample:resources")).toBe(false);
  });

  it("removes old aliases and styles while retaining Core sections", () => {
    const remove = vi.fn();
    vi.stubGlobal("document", {
      head: { appendChild: vi.fn() },
      createElement: () => ({ remove }),
    });
    const sample = plugin("sample");
    registerRuntimeExtensions([
      {
        ...sample,
        sections: [{ id: "sample-screen", view: "screen", routeAliases: ["sample-old"] }],
        styles: [sample.entry.replace("index.js", "style.css")],
      },
    ]);
    expect(resolveAdminSectionId("sample-old")).toBe("sample-screen");
    registerRuntimeExtensions([{ ...sample, sections: [{ id: "support", view: "screen" }] }]);
    expect(remove).toHaveBeenCalledOnce();
    expect(resolveAdminSectionId("sample-old")).toBe("");
    registerRuntimeExtensions([]);
    expect(ADMIN_SECTIONS.filter((section) => section.id === "support")).toHaveLength(1);
    expect(ADMIN_SECTIONS.find((section) => section.id === "support")?.component).toBeUndefined();
  });
});

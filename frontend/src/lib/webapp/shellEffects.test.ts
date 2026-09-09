import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyThemeDocumentEffects,
  applyThemeRootTokens,
  closeDisabledEmailAuthDialogs,
  syncShellBillingSelection,
  syncShellEmailAvatar,
} from "./shellEffects.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("shell effects", () => {
  it("applies theme color scheme and body background", () => {
    const documentElement = { style: { colorScheme: "" } };
    const body = { style: { backgroundColor: "" } };
    vi.stubGlobal("document", { body, documentElement });

    applyThemeDocumentEffects({
      tokens: { bg: "#101820", color_scheme: "light" },
    });

    expect(documentElement.style.colorScheme).toBe("light");
    expect(body.style.backgroundColor).toBe("#101820");
  });

  it("leaves theme effects alone without theme tokens", () => {
    const documentElement = { style: { colorScheme: "" } };
    const body = { style: { backgroundColor: "" } };
    vi.stubGlobal("document", { body, documentElement });

    applyThemeDocumentEffects(null);

    expect(documentElement.style.colorScheme).toBe("");
    expect(body.style.backgroundColor).toBe("");
  });

  it("mirrors theme tokens onto the document element and drops stale ones", () => {
    const properties = new Map<string, string>();
    const classes = new Set<string>();
    const documentElement = {
      style: {
        setProperty: (name: string, value: string) => void properties.set(name, value),
        removeProperty: (name: string) => void properties.delete(name),
      },
      classList: {
        add: (name: string) => void classes.add(name),
        remove: (name: string) => void classes.delete(name),
      },
    };
    vi.stubGlobal("document", { body: { style: {} }, documentElement });

    applyThemeRootTokens(
      "--accent:#00fe7a;--bg:#03070b;--font-sans:Inter, Arial, sans-serif",
      "theme-key-dark theme-variant-dark"
    );
    expect(properties.get("--accent")).toBe("#00fe7a");
    expect(properties.get("--font-sans")).toBe("Inter, Arial, sans-serif");
    expect(classes).toEqual(new Set(["theme-key-dark", "theme-variant-dark"]));

    // Switching to a theme that does not define --bg must not leave the old
    // value behind on the document element.
    applyThemeRootTokens("--accent:#10b981", "theme-key-windows95 theme-variant-light");
    expect(properties.get("--accent")).toBe("#10b981");
    expect(properties.has("--bg")).toBe(false);
    expect(classes).toEqual(new Set(["theme-key-windows95", "theme-variant-light"]));
  });

  it("clears a stale inline body background for CSS-file themes", () => {
    const documentElement = { style: { colorScheme: "" } };
    const body = { style: { backgroundColor: "#03070b" } };
    vi.stubGlobal("document", { body, documentElement });

    applyThemeDocumentEffects({ tokens: { color_scheme: "light" } });

    expect(body.style.backgroundColor).toBe("");
  });

  it("closes email auth dialogs only when email auth is disabled", () => {
    const closeLinkEmailDialog = vi.fn();
    const closeSetPasswordDialog = vi.fn();

    closeDisabledEmailAuthDialogs({
      closeLinkEmailDialog,
      closeSetPasswordDialog,
      emailAuthEnabled: false,
      linkEmailOpen: true,
      setPasswordOpen: true,
    });

    expect(closeLinkEmailDialog).toHaveBeenCalledOnce();
    expect(closeSetPasswordDialog).toHaveBeenCalledOnce();

    closeDisabledEmailAuthDialogs({
      closeLinkEmailDialog,
      closeSetPasswordDialog,
      emailAuthEnabled: true,
      linkEmailOpen: true,
      setPasswordOpen: true,
    });

    expect(closeLinkEmailDialog).toHaveBeenCalledOnce();
    expect(closeSetPasswordDialog).toHaveBeenCalledOnce();
  });

  it("applies billing selection patches when reconciliation changes state", () => {
    const applyPatch = vi.fn();
    const plan = { id: "monthly" };

    const patch = syncShellBillingSelection({
      applyPatch,
      input: {
        methods: [{ id: "card" }],
        plans: [plan],
        selectedTariffPlans: [],
        singleTariffMode: false,
        tariffCatalog: [],
        tariffMode: false,
      },
      state: {
        paymentStep: "tariff",
        selectedMethod: "",
        selectedPlan: null,
        selectedTariffKey: "",
      },
    });

    expect(patch).toEqual({ selectedMethod: "card", selectedPlan: plan });
    expect(applyPatch).toHaveBeenCalledWith(patch);
  });

  it("does not apply a billing patch when state is already valid", () => {
    const applyPatch = vi.fn();
    const plan = { id: "monthly" };

    const patch = syncShellBillingSelection({
      applyPatch,
      input: {
        methods: [{ id: "card" }],
        plans: [plan],
        selectedTariffPlans: [],
        singleTariffMode: false,
        tariffCatalog: [],
        tariffMode: false,
      },
      state: {
        paymentStep: "tariff",
        selectedMethod: "card",
        selectedPlan: plan,
        selectedTariffKey: "",
      },
    });

    expect(patch).toBeNull();
    expect(applyPatch).not.toHaveBeenCalled();
  });

  it("delegates email avatar syncing", () => {
    const emailAvatarSync = { sync: vi.fn() };
    const setEmailAvatarUrl = vi.fn();

    syncShellEmailAvatar({
      email: "user@example.test",
      emailAvatarSync,
      setEmailAvatarUrl,
    });

    expect(emailAvatarSync.sync).toHaveBeenCalledWith("user@example.test", setEmailAvatarUrl);
  });
});

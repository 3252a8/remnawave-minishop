import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyThemeDocumentEffects,
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

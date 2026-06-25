import { describe, expect, it, vi } from "vitest";

import { createAccountUiActions } from "./accountUiActions.js";

function makeActions(overrides = {}) {
  const state = {
    emailAuthEnabled: true,
    isDemoAuthLogin: false,
    openedAt: 0,
    startLink: "https://t.me/example_bot",
    telegram: null,
  };
  const accountStore = {
    continueTelegramLinkPendingAction: vi.fn(() => "continued"),
    linkTelegramAndActivateTrial: vi.fn(() => "trial"),
    linkTelegramAndClaimReferralWelcome: vi.fn(() => "referral"),
    openLinkEmailDialog: vi.fn(),
    openSetPasswordDialog: vi.fn(),
  };
  const deps = {
    accountStore,
    demoEmail: vi.fn(() => "demo@example.test"),
    emailAuthEnabled: () => state.emailAuthEnabled,
    getTelegram: () => state.telegram,
    getTelegramNotificationsStartLink: () => state.startLink,
    isDemoAuthLogin: () => state.isDemoAuthLogin,
    markTelegramNotificationsBotOpened: vi.fn((openedAt) => {
      state.openedAt = openedAt;
    }),
    now: () => 12345,
    openExternalLink: vi.fn(),
    refreshTelegram: vi.fn(() => null),
    setTelegram: vi.fn((telegram) => {
      state.telegram = telegram;
    }),
    showToast: vi.fn(),
    t: vi.fn((key) => key),
    ...overrides.deps,
  };
  Object.assign(state, overrides.state);
  return {
    accountStore,
    actions: createAccountUiActions(deps),
    deps,
    state,
  };
}

describe("createAccountUiActions", () => {
  it("guards email dialogs when email auth is disabled", () => {
    const { accountStore, actions } = makeActions({ state: { emailAuthEnabled: false } });

    actions.openSettingsLinkEmailDialog();
    actions.openSettingsSetPasswordDialog();

    expect(accountStore.openLinkEmailDialog).not.toHaveBeenCalled();
    expect(accountStore.openSetPasswordDialog).not.toHaveBeenCalled();
  });

  it("opens link-email dialog with demo email only during demo auth", () => {
    const demo = makeActions({ state: { isDemoAuthLogin: true } });
    const real = makeActions();

    demo.actions.openSettingsLinkEmailDialog();
    real.actions.openSettingsLinkEmailDialog();

    expect(demo.accountStore.openLinkEmailDialog).toHaveBeenCalledWith("demo@example.test");
    expect(real.accountStore.openLinkEmailDialog).toHaveBeenCalledWith("");
  });

  it("delegates account telegram follow-up actions", () => {
    const { accountStore, actions } = makeActions();

    expect(actions.continueTelegramLinkPendingAction()).toBe("continued");
    expect(actions.linkTelegramAndActivateTrial()).toBe("trial");
    expect(actions.linkTelegramAndClaimReferralWelcome()).toBe("referral");

    expect(accountStore.continueTelegramLinkPendingAction).toHaveBeenCalledOnce();
    expect(accountStore.linkTelegramAndActivateTrial).toHaveBeenCalledOnce();
    expect(accountStore.linkTelegramAndClaimReferralWelcome).toHaveBeenCalledOnce();
  });

  it("shows an unavailable toast when notification link is empty", () => {
    const { actions, deps, state } = makeActions({ state: { startLink: "" } });

    actions.openTelegramNotificationsBot();

    expect(state.openedAt).toBe(12345);
    expect(deps.showToast).toHaveBeenCalledWith("wa_telegram_notifications_link_unavailable");
    expect(deps.openExternalLink).not.toHaveBeenCalled();
  });

  it("opens t.me notification links through Telegram when possible", () => {
    const telegram = { openTelegramLink: vi.fn() };
    const { actions, deps } = makeActions({ state: { telegram } });

    actions.openTelegramNotificationsBot();

    expect(deps.setTelegram).toHaveBeenCalledWith(telegram);
    expect(telegram.openTelegramLink).toHaveBeenCalledWith("https://t.me/example_bot");
    expect(deps.openExternalLink).not.toHaveBeenCalled();
  });

  it("falls back to a generic external link when Telegram opening fails", () => {
    const telegram = {
      openTelegramLink: vi.fn(() => {
        throw new Error("nope");
      }),
    };
    const { actions, deps } = makeActions({ state: { telegram } });

    actions.openTelegramNotificationsBot();

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://t.me/example_bot");
  });
});

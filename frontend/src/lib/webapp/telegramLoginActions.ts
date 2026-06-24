type TelegramAuthSource = "auth_data";

type TelegramLoginAuthStore = {
  finalizeTelegramAuth: (authData: unknown, source: TelegramAuthSource) => unknown;
  openTelegramLogin: (
    telegramOAuthClientId: number | string | null,
    getTelegramMiniAppInitData: () => string
  ) => unknown;
};

type TelegramLoginActionDeps = {
  authStore: TelegramLoginAuthStore;
  getDemoTelegramAuthPayload: () => unknown;
  getTelegramMiniAppInitData: () => string;
  getTelegramOAuthClientId: () => number | string | null;
  isDemoAuthLogin: () => boolean;
};

export function createTelegramLoginActions({
  authStore,
  getDemoTelegramAuthPayload,
  getTelegramMiniAppInitData,
  getTelegramOAuthClientId,
  isDemoAuthLogin,
}: TelegramLoginActionDeps) {
  async function openLoginTelegram() {
    if (isDemoAuthLogin()) {
      await authStore.finalizeTelegramAuth(getDemoTelegramAuthPayload(), "auth_data");
      return;
    }
    await authStore.openTelegramLogin(getTelegramOAuthClientId(), getTelegramMiniAppInitData);
  }

  return { openLoginTelegram };
}

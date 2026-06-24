type ResumeState = {
  botOpenedAt: number;
  lastCheckAt: number;
  mode: string;
  needPrompt: boolean;
  refreshBusy: boolean;
};

type RefreshTelegramNotificationsDeps = {
  cooldownMs: number;
  loadData: () => Promise<unknown>;
  now?: () => number;
  readState: () => ResumeState;
  setBotOpenedAt: (openedAt: number) => void;
  setLastCheckAt: (checkedAt: number) => void;
  setRefreshBusy: (busy: boolean) => void;
};

export async function refreshTelegramNotificationsAfterResume({
  cooldownMs,
  loadData,
  now = Date.now,
  readState,
  setBotOpenedAt,
  setLastCheckAt,
  setRefreshBusy,
}: RefreshTelegramNotificationsDeps) {
  const state = readState();
  if (state.mode !== "app" || !state.needPrompt || !state.botOpenedAt || state.refreshBusy) {
    return;
  }
  const checkedAt = now();
  if (checkedAt - state.lastCheckAt < cooldownMs) return;
  setLastCheckAt(checkedAt);
  setRefreshBusy(true);
  try {
    await loadData();
    if (!readState().needPrompt) setBotOpenedAt(0);
  } catch (_error) {
    void _error;
  } finally {
    setRefreshBusy(false);
  }
}

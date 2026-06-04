import { writable } from "svelte/store";

export function createBroadcastStore({ api, onToast, at }) {
  const state = writable({
    broadcastTarget: "all",
    broadcastText: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: null,
  });

  const BROADCAST_TARGET_OPTIONS = [
    { value: "all", label: at("broadcast_target_all", {}, "Все активные") },
    { value: "active", label: at("broadcast_target_active", {}, "С подпиской") },
    { value: "inactive", label: at("broadcast_target_inactive", {}, "Без подписки") },
    { value: "expired", label: at("broadcast_target_expired", {}, "Expired subscription") },
    {
      value: "never",
      label: at("broadcast_target_never", {}, "Без подписки и без истории"),
    },
  ];

  async function loadCounts() {
    try {
      const res = await api("/admin/broadcast/audience-counts");
      if (res?.ok && res.counts) {
        state.update((s) => ({ ...s, broadcastCounts: res.counts }));
      }
    } catch {
      // Counts are advisory; ignore failures and keep plain labels.
    }
  }

  async function runBroadcast() {
    let text = "";
    let target = "";
    state.update((s) => {
      text = s.broadcastText;
      target = s.broadcastTarget;
      s.broadcastBusy = true;
      s.broadcastResult = null;
      return s;
    });

    try {
      const res = await api("/admin/broadcast", {
        method: "POST",
        body: JSON.stringify({ target, text }),
      });
      if (res?.ok) {
        state.update((s) => ({
          ...s,
          broadcastText: "",
          broadcastResult: { queued: res.queued || 0, failed: res.failed || 0 },
        }));
        onToast(at("broadcast_started", {}, "Рассылка запущена"));
      } else {
        onToast(res?.error || at("broadcast_failed", {}, "Ошибка рассылки"));
      }
    } finally {
      state.update((s) => ({ ...s, broadcastBusy: false }));
    }
  }

  function updateField(fields) {
    state.update((s) => ({ ...s, ...fields }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    runBroadcast,
    updateField,
    loadCounts,
    BROADCAST_TARGET_OPTIONS,
  };
}

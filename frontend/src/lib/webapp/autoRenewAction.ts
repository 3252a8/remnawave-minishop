import type { BillingActions } from "./billingActions";

type LoadData = (options: { fresh?: boolean; preserveView?: boolean }) => Promise<unknown>;
type Translate = (key: string) => string;

type AutoRenewActionDeps = {
  billing: Pick<BillingActions, "postAutoRenew">;
  getBusy: () => boolean;
  loadData: LoadData;
  openExternalLink: (url: string) => void;
  setCreatorCancelStep: (step: 0 | 1 | 2) => void;
  setBusy: (busy: boolean) => void;
  showToast: (message: unknown) => void;
  t: Translate;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function createAutoRenewAction({
  billing,
  getBusy,
  loadData,
  openExternalLink,
  setCreatorCancelStep,
  setBusy,
  showToast,
  t,
}: AutoRenewActionDeps) {
  async function toggleAutoRenew(enabled: boolean) {
    if (getBusy()) return;
    setBusy(true);
    try {
      const response = await billing.postAutoRenew(enabled);
      if (!response.ok) throw response;
      showToast(
        response.auto_renew_enabled ? t("wa_auto_renew_enabled") : t("wa_auto_renew_disabled")
      );
      await loadData({ fresh: true, preserveView: true });
    } catch (error: unknown) {
      const errorRecord = asRecord(error);
      if (errorRecord.error === "auto_renew_requires_saved_method") {
        showToast(t("wa_auto_renew_requires_saved_method"));
      } else if (!enabled && errorRecord.error === "auto_renew_tribute_cancel_required") {
        setCreatorCancelStep(1);
      } else if (errorRecord.error === "auto_renew_provider_cancel_failed") {
        // The mandate is still live upstream, so say so instead of echoing the
        // English backend message.
        showToast(t("wa_auto_renew_provider_cancel_failed"));
      } else {
        showToast(errorRecord.message || t("wa_auto_renew_update_failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  function closeCreatorCancelDialog() {
    if (!getBusy()) setCreatorCancelStep(0);
  }

  function openCreatorCancelConfirmation() {
    if (!getBusy()) setCreatorCancelStep(2);
  }

  function backToCreatorCancelOptions() {
    if (!getBusy()) setCreatorCancelStep(1);
  }

  async function confirmCreatorCancellation() {
    if (getBusy()) return;
    setBusy(true);
    try {
      const response = await billing.postAutoRenew(false, true);
      if (!response.ok) throw response;
      setCreatorCancelStep(0);
      showToast(t("wa_auto_renew_disabled"));
      await loadData({ fresh: true, preserveView: true });
    } catch (error: unknown) {
      const record = asRecord(error);
      showToast(record.message || t("wa_auto_renew_update_failed"));
    } finally {
      setBusy(false);
    }
  }

  function openCreatorCancellationLink() {
    openExternalLink("https://t.me/tribute");
  }

  return {
    toggleAutoRenew,
    closeCreatorCancelDialog,
    openCreatorCancelConfirmation,
    backToCreatorCancelOptions,
    confirmCreatorCancellation,
    openCreatorCancellationLink,
  };
}

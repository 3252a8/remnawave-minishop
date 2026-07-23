import type { BillingActions } from "./billingActions";

type LoadData = (options: { fresh?: boolean; preserveView?: boolean }) => Promise<unknown>;
type Translate = (key: string) => string;

type SubscriptionReissueActionDeps = {
  billing: Pick<BillingActions, "postSubscriptionReissue">;
  getBusy: () => boolean;
  loadData: LoadData;
  refreshDevices: () => Promise<unknown> | unknown;
  setBusy: (busy: boolean) => void;
  setDialogOpen: (open: boolean) => void;
  showToast: (message: unknown) => void;
  t: Translate;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function createSubscriptionReissueAction({
  billing,
  getBusy,
  loadData,
  refreshDevices,
  setBusy,
  setDialogOpen,
  showToast,
  t,
}: SubscriptionReissueActionDeps) {
  function openSubscriptionReissueDialog() {
    if (getBusy()) return;
    setDialogOpen(true);
  }

  function closeSubscriptionReissueDialog() {
    if (getBusy()) return;
    setDialogOpen(false);
  }

  async function confirmSubscriptionReissue() {
    if (getBusy()) return;
    setBusy(true);
    try {
      const response = await billing.postSubscriptionReissue();
      if (!response.ok) throw response;
      showToast(
        response.email_sent
          ? t("wa_subscription_reissue_done")
          : t("wa_subscription_reissue_done_email_failed")
      );
      setDialogOpen(false);
      await loadData({ fresh: true, preserveView: true });
      await refreshDevices();
    } catch (error: unknown) {
      const errorRecord = asRecord(error);
      if (errorRecord.error === "email_required") {
        showToast(t("wa_subscription_reissue_email_required"));
      } else if (errorRecord.error === "subscription_not_active") {
        showToast(t("wa_subscription_reissue_requires_subscription"));
      } else {
        showToast(errorRecord.message || t("wa_subscription_reissue_failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return {
    openSubscriptionReissueDialog,
    closeSubscriptionReissueDialog,
    confirmSubscriptionReissue,
  };
}

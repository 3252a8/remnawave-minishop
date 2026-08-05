import type { BillingActions } from "./billingActions";

type LoadData = (options: { fresh?: boolean; preserveView?: boolean }) => Promise<unknown>;
type Translate = (key: string) => string;

type AutoRenewActionDeps = {
  billing: Pick<BillingActions, "postAutoRenew">;
  getBusy: () => boolean;
  loadData: LoadData;
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
      } else {
        showToast(errorRecord.message || t("wa_auto_renew_update_failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return { toggleAutoRenew };
}

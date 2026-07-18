export type TelegramWebApp = Record<string, unknown> & {
  openInvoice?: (url: string, callback: (status: string) => void) => void;
};

type TelegramInvoiceSdk = {
  ensureForAction?: () => Promise<TelegramWebApp | null>;
  hasLaunchParams?: () => boolean;
  refresh?: () => TelegramWebApp | null;
} | null;

type OpenTelegramInvoiceOptions = {
  getTg?: (() => TelegramWebApp | null) | null;
  onFailed: () => void;
  onPaid: () => Promise<void> | void;
  onUnavailable: () => void;
  telegramSdk?: TelegramInvoiceSdk;
  tg?: TelegramWebApp | null;
  url: string;
};

function resolveTelegramWebApp({
  getTg,
  telegramSdk,
  tg,
}: Pick<OpenTelegramInvoiceOptions, "getTg" | "telegramSdk" | "tg">): TelegramWebApp | null {
  const currentTg = getTg?.();
  if (currentTg) return currentTg;
  if (tg) return tg;
  return telegramSdk?.refresh?.() || null;
}

export async function openTelegramInvoice({
  getTg,
  onFailed,
  onPaid,
  onUnavailable,
  telegramSdk = null,
  tg = null,
  url,
}: OpenTelegramInvoiceOptions): Promise<boolean> {
  if (!url) return false;
  let invoiceTg: TelegramWebApp | null = null;
  if (!telegramSdk?.hasLaunchParams || telegramSdk.hasLaunchParams()) {
    invoiceTg = resolveTelegramWebApp({ getTg, telegramSdk, tg });
    if (!invoiceTg?.openInvoice && telegramSdk?.ensureForAction) {
      invoiceTg = await telegramSdk.ensureForAction();
    }
    if (!invoiceTg?.openInvoice) {
      invoiceTg = resolveTelegramWebApp({ getTg, telegramSdk, tg });
    }
  }
  if (!invoiceTg?.openInvoice) {
    onUnavailable();
    return false;
  }
  invoiceTg.openInvoice(url, async (status) => {
    if (status === "paid") await onPaid();
    else if (status === "failed") onFailed();
  });
  return true;
}

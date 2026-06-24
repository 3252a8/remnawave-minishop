import { copyTextToClipboard } from "./clipboard.js";

type ClipboardActionDeps = {
  copyTextToClipboard?: (value: string) => Promise<boolean>;
  showToast: (message: unknown) => void;
  t: (key: string) => string;
};

export function createClipboardActions({
  copyTextToClipboard: copyText = copyTextToClipboard,
  showToast,
  t,
}: ClipboardActionDeps) {
  async function copyTextValue(value: string, success = t("wa_copied")) {
    if (!(await copyText(value))) {
      showToast(t("wa_unavailable"));
      return;
    }
    showToast(success);
  }

  return { copyText: copyTextValue };
}

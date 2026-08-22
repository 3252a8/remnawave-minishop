type ClipboardNavigator = {
  clipboard?: {
    writeText?: (value: string) => Promise<void>;
  };
};

type ClipboardTextArea = {
  focus: () => void;
  remove: () => void;
  select: () => void;
  setAttribute: (name: "readonly", value: string) => void;
  setSelectionRange: (start: number, end: number) => void;
  style: {
    height: string;
    left: string;
    opacity: string;
    pointerEvents: string;
    position: string;
    top: string;
    width: string;
  };
  value: string;
};

type ClipboardDocument = {
  body: {
    appendChild: (node: ClipboardTextArea) => void;
  };
  createElement: (tagName: "textarea") => ClipboardTextArea;
  execCommand: (command: "copy") => boolean;
};

export type CopyTextOptions = {
  documentRef?: ClipboardDocument;
  navigatorRef?: ClipboardNavigator;
};

function browserDocument(): ClipboardDocument {
  return {
    body: {
      appendChild: (node) => {
        document.body.appendChild(node as HTMLTextAreaElement);
      },
    },
    createElement: (tagName) => document.createElement(tagName),
    execCommand: (command) => document.execCommand(command),
  };
}

export async function copyTextToClipboard(value: string, options: CopyTextOptions = {}) {
  if (!value) return false;
  const navigatorRef = options.navigatorRef || (typeof navigator === "undefined" ? {} : navigator);
  try {
    if (!navigatorRef.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigatorRef.clipboard.writeText(value);
    return true;
  } catch {
    // Telegram's iOS WebView may expose no Clipboard API (or reject it), so
    // keep the legacy copy inside the original click activation when possible.
    if (!options.documentRef && typeof document === "undefined") return false;
    const documentRef = options.documentRef || browserDocument();
    const area = documentRef.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.left = "0";
    area.style.width = "1px";
    area.style.height = "1px";
    area.style.opacity = "0";
    area.style.pointerEvents = "none";
    documentRef.body.appendChild(area);
    try {
      area.focus();
      area.select();
      area.setSelectionRange(0, value.length);
      return documentRef.execCommand("copy");
    } catch {
      return false;
    } finally {
      area.remove();
    }
  }
}

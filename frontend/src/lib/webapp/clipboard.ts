type ClipboardNavigator = {
  clipboard?: {
    writeText?: (value: string) => Promise<void>;
  };
};

type ClipboardTextArea = {
  remove: () => void;
  select: () => void;
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
  const navigatorRef = options.navigatorRef || navigator;
  try {
    if (!navigatorRef.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigatorRef.clipboard.writeText(value);
    return true;
  } catch {
    const documentRef = options.documentRef || browserDocument();
    const area = documentRef.createElement("textarea");
    area.value = value;
    documentRef.body.appendChild(area);
    area.select();
    documentRef.execCommand("copy");
    area.remove();
    return true;
  }
}

import { describe, expect, it, vi } from "vitest";

import { copyTextToClipboard } from "./clipboard.js";

function makeDocument(copyResult = true) {
  const area = {
    focus: vi.fn(),
    remove: vi.fn(),
    select: vi.fn(),
    setAttribute: vi.fn(),
    setSelectionRange: vi.fn(),
    style: {
      height: "",
      left: "",
      opacity: "",
      pointerEvents: "",
      position: "",
      top: "",
      width: "",
    },
    value: "",
  };
  return {
    area,
    body: {
      appendChild: vi.fn(),
    },
    createElement: vi.fn(() => area),
    execCommand: vi.fn(() => copyResult),
  };
}

describe("copyTextToClipboard", () => {
  it("skips empty text", async () => {
    const navigatorRef = { clipboard: { writeText: vi.fn() } };

    await expect(copyTextToClipboard("", { navigatorRef })).resolves.toBe(false);

    expect(navigatorRef.clipboard.writeText).not.toHaveBeenCalled();
  });

  it("uses navigator.clipboard when available", async () => {
    const navigatorRef = { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } };
    const documentRef = makeDocument();

    await expect(copyTextToClipboard("token", { documentRef, navigatorRef })).resolves.toBe(true);

    expect(navigatorRef.clipboard.writeText).toHaveBeenCalledWith("token");
    expect(documentRef.createElement).not.toHaveBeenCalled();
  });

  it("falls back to textarea copy when clipboard write fails", async () => {
    const navigatorRef = {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error("denied")),
      },
    };
    const documentRef = makeDocument();

    await expect(copyTextToClipboard("backup", { documentRef, navigatorRef })).resolves.toBe(true);

    expect(documentRef.createElement).toHaveBeenCalledWith("textarea");
    expect(documentRef.area.value).toBe("backup");
    expect(documentRef.area.setAttribute).toHaveBeenCalledWith("readonly", "");
    expect(documentRef.body.appendChild).toHaveBeenCalledWith(documentRef.area);
    expect(documentRef.area.focus).toHaveBeenCalledOnce();
    expect(documentRef.area.select).toHaveBeenCalledOnce();
    expect(documentRef.area.setSelectionRange).toHaveBeenCalledWith(0, 6);
    expect(documentRef.execCommand).toHaveBeenCalledWith("copy");
    expect(documentRef.area.remove).toHaveBeenCalledOnce();
  });

  it("reports a failed fallback and still removes the textarea", async () => {
    const documentRef = makeDocument(false);

    await expect(copyTextToClipboard("backup", { documentRef, navigatorRef: {} })).resolves.toBe(
      false
    );

    expect(documentRef.execCommand).toHaveBeenCalledWith("copy");
    expect(documentRef.area.remove).toHaveBeenCalledOnce();
  });
});

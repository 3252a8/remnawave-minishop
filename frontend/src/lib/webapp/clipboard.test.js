import { describe, expect, it, vi } from "vitest";

import { copyTextToClipboard } from "./clipboard.js";

function makeDocument() {
  const area = {
    remove: vi.fn(),
    select: vi.fn(),
    value: "",
  };
  return {
    area,
    body: {
      appendChild: vi.fn(),
    },
    createElement: vi.fn(() => area),
    execCommand: vi.fn(() => true),
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
    expect(documentRef.body.appendChild).toHaveBeenCalledWith(documentRef.area);
    expect(documentRef.area.select).toHaveBeenCalledOnce();
    expect(documentRef.execCommand).toHaveBeenCalledWith("copy");
    expect(documentRef.area.remove).toHaveBeenCalledOnce();
  });
});

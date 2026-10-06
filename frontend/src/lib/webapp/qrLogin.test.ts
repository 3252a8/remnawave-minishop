import { describe, expect, it } from "vitest";

import { parseQrLoginCode, qrLoginSiteLabel, telegramQrScanner } from "./qrLogin";

const CODE = "AbCdEfGhIjKlMnOpQr_s-t";

describe("parseQrLoginCode", () => {
  it("reads the code from the shop's sign-in link or a bare code", () => {
    expect(parseQrLoginCode(`https://shop.example/settings#qrlogin=${CODE}`)).toBe(CODE);
    expect(parseQrLoginCode(`#qrlogin=${CODE}`)).toBe(CODE);
    expect(parseQrLoginCode(` ${CODE} `)).toBe(CODE);
  });

  it("rejects anything that is not a sign-in code", () => {
    expect(parseQrLoginCode("https://t.me/some_bot?start=webapp_auth_x")).toBeNull();
    expect(parseQrLoginCode(`https://shop.example/#qrlogin=${CODE}extra`)).toBeNull();
    expect(parseQrLoginCode("vless://uuid@host:443")).toBeNull();
    expect(parseQrLoginCode("")).toBeNull();
  });
});

describe("telegramQrScanner", () => {
  const scanner = { showScanQrPopup: () => undefined, isVersionAtLeast: () => true };

  it("uses Telegram's scanner only in the phone apps", () => {
    expect(telegramQrScanner({ ...scanner, platform: "ios" })).not.toBeNull();
    expect(telegramQrScanner({ ...scanner, platform: "android" })).not.toBeNull();
    expect(telegramQrScanner({ ...scanner, platform: "tdesktop" })).toBeNull();
    expect(
      telegramQrScanner({ ...scanner, platform: "ios", isVersionAtLeast: () => false })
    ).toBeNull();
    expect(telegramQrScanner(null)).toBeNull();
  });
});

describe("qrLoginSiteLabel", () => {
  it("shows only the host people need to type", () => {
    expect(qrLoginSiteLabel("https://shop.example")).toBe("shop.example");
    expect(qrLoginSiteLabel("https://shop.example:8443/")).toBe("shop.example:8443");
  });

  it("falls back to nothing when the shop has no public address", () => {
    expect(qrLoginSiteLabel("")).toBe("");
    expect(qrLoginSiteLabel(undefined)).toBe("");
    expect(qrLoginSiteLabel("not a url")).toBe("");
  });
});

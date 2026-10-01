export const DEVICE_NAME_MAX_LENGTH = 32;

/** Match the server's normalization before checking the name's code point length. */
export function normalizeDeviceName(value: string): string {
  return Array.from(value.normalize("NFC"), (char) => {
    if (/[\p{Cc}\p{Zl}\p{Zp}]/u.test(char)) return " ";
    if (/[\p{Cf}\p{Cs}]/u.test(char) && char !== "\u200c" && char !== "\u200d") return "";
    return char;
  })
    .join("")
    .replace(/\s+/g, " ")
    .trim()
    .normalize("NFC");
}

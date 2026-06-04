function bytesToHex(buffer) {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(value) {
  const data = new TextEncoder().encode(value);
  const hashBuffer = await globalThis.crypto?.subtle?.digest("SHA-256", data);
  return bytesToHex(hashBuffer);
}

export async function buildGravatarUrl(emailValue) {
  const email = String(emailValue || "")
    .trim()
    .toLowerCase();
  if (!email || !globalThis.crypto?.subtle) return "";
  try {
    const hash = await sha256Hex(email);
    return `https://www.gravatar.com/avatar/${hash}?d=identicon&s=160`;
  } catch {
    return "";
  }
}

export function resolveProfileAvatarUrl(user, emailAvatarUrl = "") {
  const telegramAvatar = String(user?.telegram_photo_url || "").trim();
  if (user?.telegram_linked && telegramAvatar) return telegramAvatar;
  return String(emailAvatarUrl || "").trim();
}

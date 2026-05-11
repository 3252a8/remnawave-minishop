function bytesToHex(buffer) {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(value) {
  const data = new TextEncoder().encode(value);
  const hashBuffer = await window.crypto.subtle.digest("SHA-256", data);
  return bytesToHex(hashBuffer);
}

export async function buildGravatarUrl(emailValue) {
  if (!emailValue || !window.crypto?.subtle) return "";
  try {
    const hash = await sha256Hex(emailValue);
    return `https://www.gravatar.com/avatar/${hash}?d=mp&s=160`;
  } catch {
    return "";
  }
}

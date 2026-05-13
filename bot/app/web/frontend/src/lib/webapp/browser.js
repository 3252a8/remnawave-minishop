export function readJsonScript(id) {
  const node = document.getElementById(id);
  if (!node || !node.textContent) return null;
  try {
    return JSON.parse(node.textContent);
  } catch (error) {
    console.warn(`Failed to parse JSON config from #${id}`, error);
    return null;
  }
}

export function structuredCloneSafe(value) {
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value));
  }
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function normalizeBrand(brand = {}) {
  return {
    title: String(brand.title || "/minishop").trim() || "/minishop",
    logoUrl: String(brand.logoUrl || "").trim(),
    emoji: String(brand.emoji || brand.logoEmoji || "🫥").trim() || "🫥",
    emojiFont: String(brand.emojiFont || brand.logoEmojiFont || "system").trim() || "system",
  };
}

export function emojiToCodepoints(value) {
  return Array.from(String(value || "").trim())
    .map((char) => char.codePointAt(0)?.toString(16))
    .filter(Boolean)
    .join("_");
}

export function animatedEmojiAssetUrls(emoji) {
  const codepoints = emojiToCodepoints(emoji);
  if (!codepoints) return { gif: "", webp: "" };
  return {
    gif: `/webapp-emoji/${codepoints}/512.gif`,
    webp: `/webapp-emoji/${codepoints}/512.webp`,
  };
}

export function brandFaviconHref(brand = {}) {
  const normalizedBrand = normalizeBrand(brand);
  if (normalizedBrand.logoUrl) return normalizedBrand.logoUrl;

  if (normalizedBrand.emojiFont === "noto-color-animated") {
    return animatedEmojiAssetUrls(normalizedBrand.emoji).gif;
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="52">${escapeHtml(normalizedBrand.emoji)}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function applyFavicon(brand = {}) {
  if (typeof document === "undefined") return;
  const favicon = document.getElementById("app-favicon");
  if (!favicon) return;

  const href = brandFaviconHref(brand);
  favicon.setAttribute("href", href);
  if (href.startsWith("data:image/svg+xml")) {
    favicon.setAttribute("type", "image/svg+xml");
  } else if (href.endsWith(".gif")) {
    favicon.setAttribute("type", "image/gif");
  } else if (href.endsWith(".webp")) {
    favicon.setAttribute("type", "image/webp");
  } else {
    favicon.removeAttribute("type");
  }
}

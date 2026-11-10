type LocationLike = {
  hash?: string;
  href?: string;
};

export function hasControlChars(value: unknown): boolean {
  return Array.from(String(value || "")).some((char) => {
    const code = char.charCodeAt(0);
    return code <= 31 || code === 127;
  });
}

export function isUnsafeAppUrl(value: unknown): boolean {
  return (
    !String(value || "").trim() ||
    hasControlChars(value) ||
    /^(?:javascript|data|vbscript):/i.test(String(value || "").trim())
  );
}

export function isHttpUrl(value: unknown): boolean {
  return /^https?:\/\//i.test(String(value || "").trim());
}

export function isExternalAppLaunchPath(pathname: unknown): boolean {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  return normalized === "/open-app";
}

export function readExternalAppLaunchTarget(locationRef: LocationLike | null = null): string {
  const ref = locationRef || (typeof window === "undefined" ? null : window.location);
  if (!ref?.hash) return "";

  const target = String(new URLSearchParams(ref.hash.replace(/^#/, "")).get("url") || "").trim();
  if (isUnsafeAppUrl(target) || isHttpUrl(target)) return "";
  return target;
}

export function buildExternalAppLaunchUrl(
  value: unknown,
  locationRef: LocationLike | null = null,
  language: unknown = ""
): string {
  const target = String(value || "").trim();
  if (isUnsafeAppUrl(target) || isHttpUrl(target)) return "";

  const ref = locationRef || (typeof window === "undefined" ? null : window.location);
  if (!ref?.href) return "";

  const url = new URL("/open-app", ref.href);
  const lang = String(language || "")
    .trim()
    .toLowerCase();
  if (/^[a-z]{2}(?:-[a-z0-9]{2,8})?$/.test(lang)) {
    url.searchParams.set("lang", lang);
  }
  url.hash = new URLSearchParams({ url: target }).toString();
  return url.href;
}

export function openUrlWithHiddenAnchor(url: unknown): void {
  const target = String(url || "").trim();
  // Guard the navigation sink itself: reject javascript:/data:/vbscript: and
  // control characters inline so the scheme check is a barrier for this href /
  // location.assign sink even if a caller forgets to pre-validate.
  if (!target || hasControlChars(target) || /^(?:javascript|data|vbscript):/i.test(target)) {
    return;
  }
  try {
    const anchor = document.createElement("a");
    anchor.href = target;
    anchor.target = "_self";
    anchor.rel = "noreferrer";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } catch {
    window.location.assign(target);
  }
}

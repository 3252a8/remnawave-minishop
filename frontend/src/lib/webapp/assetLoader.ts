export function resolveWebappAssetPath(configValue: unknown, fallbackName: string) {
  const raw = String(configValue || "").trim() || fallbackName;
  if (/^(?:https?:)?\/\//i.test(raw) || raw.startsWith("data:")) return fallbackName;
  if (
    typeof window !== "undefined" &&
    window.location.protocol === "file:" &&
    raw.startsWith("/")
  ) {
    return raw.slice(1);
  }
  return raw.startsWith("/") ? raw : `/${raw}`;
}

export function appendStylesheetOnce(id: string, href: string) {
  if (!href || document.getElementById(id)) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = href;
    link.onload = () => resolve();
    link.onerror = () => {
      link.remove();
      reject(new Error(`stylesheet_load_failed:${href}`));
    };
    document.head.appendChild(link);
  });
}

export function appendScriptOnce(id: string, src: string) {
  if (!src || document.getElementById(id)) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      reject(new Error(`script_load_failed:${src}`));
    };
    document.head.appendChild(script);
  });
}

export async function appendStylesheetWithFallback(id: string, href: string, fallbackName: string) {
  const fallbackHref = resolveWebappAssetPath("", fallbackName);
  try {
    await appendStylesheetOnce(id, href);
  } catch (error) {
    if (!fallbackHref || href === fallbackHref) throw error;
    await appendStylesheetOnce(id, fallbackHref);
  }
}

export async function appendScriptWithFallback(id: string, src: string, fallbackName: string) {
  const fallbackSrc = resolveWebappAssetPath("", fallbackName);
  try {
    await appendScriptOnce(id, src);
  } catch (error) {
    if (!fallbackSrc || src === fallbackSrc) throw error;
    await appendScriptOnce(id, fallbackSrc);
  }
}

export function appendPrefetchOnce(id: string, href: string, asType = "") {
  if (typeof document === "undefined" || !href || document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "prefetch";
  link.href = href;
  if (asType) link.as = asType;
  document.head.appendChild(link);
}

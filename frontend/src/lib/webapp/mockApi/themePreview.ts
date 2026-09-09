import { strFromU8 } from "fflate";
import { themeTokensToInlineStyle } from "../themeStyle";
import type { DemoPackage } from "./themePackages";

const mime: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  ico: "image/x-icon",
  woff: "font/woff",
  woff2: "font/woff2",
  ttf: "font/ttf",
};
function dataUrl(bytes: Uint8Array, name: string) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return (
    "data:" +
    (mime[name.split(".").pop() || ""] || "application/octet-stream") +
    ";base64," +
    btoa(binary)
  );
}
export async function demoThemePreview(item: DemoPackage, variant: string): Promise<Blob> {
  const root = "/demo/runtime/themes/preview/";
  const [body, rawBase] = await Promise.all(
    ["home.html", "home.css"].map(async (name) => {
      const response = await fetch(root + name);
      if (!response.ok) throw { error: "theme_preview_unavailable" };
      return response.text();
    })
  );
  const base = rawBase
    .replace(/@font-face\s*\{[^}]*\}/gi, "")
    .replace(/url\((?!['"]?data:)[^)]*\)/gi, "none");
  const key = /^[A-Za-z0-9_-]{1,64}$/.test(item.theme.key) ? item.theme.key : "dark";
  let css = item.files[item.theme.css_file || ""]
    ? strFromU8(item.files[item.theme.css_file || ""])
    : "";
  css = css
    .replace(/@import\s[^;]+;/gi, "")
    .replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (_all, _quote: string, resource: string) => {
      let name = resource.replace("/webapp-theme-assets/" + key + "/", "").split("?")[0];
      if (!item.files[name] && item.theme.css_file?.includes("/")) {
        name = new URL(resource, "https://theme.invalid/" + item.theme.css_file).pathname.slice(1);
      }
      return item.files[name] ? 'url("' + dataUrl(item.files[name], name) + '")' : "none";
    });
  const tokens = { ...item.theme.tokens, ...item.theme.variants?.[variant] };
  const safeTokens = Object.fromEntries(
    Object.entries(tokens).filter(
      ([name, value]) =>
        /^[a-z_]+$/.test(name) &&
        (typeof value === "number" || (typeof value === "string" && !/[;{}<>]/.test(value)))
    )
  );
  const declarations = themeTokensToInlineStyle(safeTokens, undefined, { fallbackAccent: false })
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;");
  const style = (base + "\n" + css).replaceAll("<", "\\3c ");
  const policy =
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'";
  const html =
    '<!doctype html><html class="theme-' +
    (variant === "light" ? "light" : "dark") +
    " theme-key-" +
    key +
    '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="' +
    policy +
    '"><style>' +
    style +
    "</style></head><body>" +
    body
      .replace('class="app-shell', 'style="' + declarations + '" class="app-shell')
      .replaceAll("THEME_KEY_PLACEHOLDER", "theme-key-" + key)
      .replaceAll("theme-dark", "theme-" + (variant === "light" ? "light" : "dark")) +
    "</body></html>";
  return new Blob([html], { type: "text/html" });
}

import { marked, Renderer } from "marked";

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] || character;
  });
}

function safeLink(url: string): string | null {
  const value = String(url || "").trim();
  if (!value) return null;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  try {
    const parsed = new URL(value);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol) ? value : null;
  } catch {
    return null;
  }
}

function safeImage(url: string): string | null {
  try {
    const parsed = new URL(String(url || "").trim());
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

const renderer = new Renderer();
renderer.html = ({ text }) => escapeHtml(text);
renderer.link = function ({ href, title, tokens }) {
  const destination = safeLink(href);
  const label = this.parser.parseInline(tokens);
  if (!destination) return label;
  const titleAttribute = title ? ` title="${escapeHtml(title)}"` : "";
  const external = !destination.startsWith("/") && !destination.startsWith("mailto:");
  return `<a href="${escapeHtml(destination)}"${titleAttribute}${
    external ? ' target="_blank" rel="noopener noreferrer"' : ""
  }>${label}</a>`;
};
renderer.image = ({ href, title, text }) => {
  const source = safeImage(href);
  if (!source) return escapeHtml(text);
  const titleAttribute = title ? ` title="${escapeHtml(title)}"` : "";
  return `<img src="${escapeHtml(source)}" alt="${escapeHtml(text)}"${titleAttribute} loading="lazy" referrerpolicy="no-referrer">`;
};

/** Render Markdown while treating every raw HTML fragment as text and constraining URLs. */
export function renderMarkdown(markdown: unknown): string {
  return marked.parse(String(markdown || ""), {
    async: false,
    gfm: true,
    renderer,
  }) as string;
}

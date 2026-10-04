/**
 * The one pair of escape helpers the rich-text modules share.
 *
 * It lives on its own so the serializer and the link detector can both use it
 * without importing each other: every string that reaches display HTML passes
 * through `escapeHtml`, and a second copy of that rule is the kind of thing
 * that drifts.
 */

export function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function unescapeHtml(value: string): string {
  const named: Record<string, string> = {
    lt: "<",
    gt: ">",
    quot: '"',
    apos: "'",
    nbsp: " ",
    amp: "&",
  };
  // Decode once: an escaped entity must stay literal, including numeric ampersands.
  return value.replace(
    /&(#(?:x[0-9a-f]+|[0-9]+)|lt|gt|quot|apos|nbsp|amp);/gi,
    (entity: string, reference: string) => {
      if (!reference.startsWith("#")) return named[reference.toLowerCase()];
      const digits = reference.slice(1);
      const codepoint =
        digits[0].toLowerCase() === "x" ? parseInt(digits.slice(1), 16) : Number(digits);
      return codepoint > 0 && codepoint <= 0x10ffff && !(codepoint >= 0xd800 && codepoint <= 0xdfff)
        ? String.fromCodePoint(codepoint)
        : entity;
    }
  );
}

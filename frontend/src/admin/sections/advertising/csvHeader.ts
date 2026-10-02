export function csvHeader(source: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  const text = source.replace(/^\uFEFF/, "");
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (!quoted && char === delimiter) {
      cells.push(cell);
      cell = "";
    } else if (!quoted && (char === "\r" || char === "\n")) break;
    else cell += char;
  }
  if (!text || quoted) return [];
  cells.push(cell);
  return cells;
}

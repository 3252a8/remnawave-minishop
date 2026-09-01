export type CountryFlagPart = {
  kind: "flag" | "text";
  value: string;
};

const COUNTRY_FLAG_PATTERN = /\p{Regional_Indicator}{2}|\u{1f3f4}[\u{e0061}-\u{e007a}]+\u{e007f}/gu;

export function countryFlagParts(name: string): CountryFlagPart[] {
  const parts: CountryFlagPart[] = [];
  let offset = 0;

  for (const match of name.matchAll(COUNTRY_FLAG_PATTERN)) {
    const index = match.index;
    if (index > offset) parts.push({ kind: "text", value: name.slice(offset, index) });
    parts.push({ kind: "flag", value: match[0] });
    offset = index + match[0].length;
  }

  if (offset < name.length) parts.push({ kind: "text", value: name.slice(offset) });
  return parts;
}

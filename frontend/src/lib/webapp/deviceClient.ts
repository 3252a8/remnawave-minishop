interface KnownClient {
  name: string;
  pattern: RegExp;
}

function clientPattern(alias: string): RegExp {
  return new RegExp(`^(?:${alias})(?:[\\s/]+v?([0-9][\\w.+-]*))?(?=$|\\s)`, "i");
}

const KNOWN_CLIENTS: readonly KnownClient[] = [
  { name: "RabbitHole", pattern: clientPattern("rabbithole") },
  { name: "Koala Clash", pattern: clientPattern("koala[-_ ]?clash") },
  { name: "Shadowrocket", pattern: clientPattern("shadowrocket") },
  { name: "Streisand", pattern: clientPattern("streisand") },
  { name: "v2rayNG", pattern: clientPattern("v2rayng") },
  { name: "v2rayN", pattern: clientPattern("v2rayn") },
  { name: "v2RayTun", pattern: clientPattern("v2ray[-_ ]?tun") },
  {
    name: "Mihomo",
    pattern: clientPattern("(?:mihomo(?:\\s+meta)?|clash[._ -]?meta)"),
  },
  { name: "Hiddify", pattern: clientPattern("hiddify") },
  { name: "sing-box", pattern: clientPattern("(?:sing[-_ ]?box|sfa|sfi|sfm|sft)") },
  { name: "NekoBox", pattern: clientPattern("nekobox") },
  { name: "Clash Verge", pattern: clientPattern("clash[-_ ]?verge") },
  { name: "FlClash", pattern: clientPattern("flclashx?") },
  { name: "Karing", pattern: clientPattern("karing") },
  { name: "Stash", pattern: clientPattern("stash") },
  { name: "Happ", pattern: clientPattern("happ") },
  { name: "Incy", pattern: clientPattern("incy") },
];

function label(name: string, version?: string): string {
  return version ? `${name} ${version}` : name;
}

export function deviceClientLabel(userAgent: unknown): string {
  const value = String(userAgent ?? "").trim();
  if (!value) return "";

  for (const client of KNOWN_CLIENTS) {
    const match = value.match(client.pattern);
    if (match) return label(client.name, match[1]);
  }

  const product = value.match(/^([^\s/]+)(?:\/([^\s]+))?/);
  if (!product) return "";
  return label(product[1].replace(/[-_]+/g, " "), product[2]);
}

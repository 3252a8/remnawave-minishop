declare module "node:fs" {
  export function readFileSync(path: URL, encoding: "utf8"): string;
}

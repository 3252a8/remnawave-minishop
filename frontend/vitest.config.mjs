import path from "node:path";
import { fileURLToPath } from "node:url";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "src");

function firstPartyRunesOptions({ filename }) {
  if (filename && path.resolve(filename).startsWith(srcDir)) {
    return { runes: true };
  }
}

export default defineConfig({
  plugins: [
    svelte({
      dynamicCompileOptions: firstPartyRunesOptions,
    }),
  ],
  resolve: {
    alias: {
      $lib: path.resolve(__dirname, "src/lib"),
      $components: path.resolve(__dirname, "src/lib/components"),
    },
  },
  test: {
    fsModuleCache: true,
    environment: "node",
    include: ["src/**/*.{test,spec}.{js,ts}"],
  },
});

import path from "node:path";
import { fileURLToPath } from "node:url";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "src");

export default defineConfig({
  plugins: [
    svelte({
      dynamicCompileOptions({ filename }) {
        if (filename && path.resolve(filename).startsWith(srcDir)) {
          return { runes: true };
        }
      },
    }),
  ],
  resolve: {
    alias: {
      $lib: path.resolve(__dirname, "src/lib"),
      $components: path.resolve(__dirname, "src/lib/components"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.{js,ts}"],
  },
});

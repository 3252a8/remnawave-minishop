import path from "node:path";
import { fileURLToPath } from "node:url";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const templateDir = path.resolve(__dirname, "../templates");

export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: templateDir,
    emptyOutDir: false,
    minify: false,
    sourcemap: false,
    cssCodeSplit: false,
    lib: {
      entry: path.resolve(__dirname, "src/main.js"),
      name: "SubscriptionWebApp",
      formats: ["iife"],
      fileName: () => "subscription_webapp.js",
      cssFileName: "subscription_webapp",
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "subscription_webapp.css";
          }
          return "subscription_webapp.[name][extname]";
        },
      },
    },
  },
});

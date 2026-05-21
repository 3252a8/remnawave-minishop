import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const templateDir = path.resolve(__dirname, "../backend/bot/app/web/templates");

export default defineConfig(({ mode }) => {
  const isAdminBuild = mode === "admin";
  const outputBase = isAdminBuild ? "subscription_webapp_admin" : "subscription_webapp";

  return {
    resolve: {
      alias: {
        $lib: path.resolve(__dirname, "src/lib"),
        $components: path.resolve(__dirname, "src/lib/components"),
      },
    },
    plugins: [
      tailwindcss(),
      svelte({
        compilerOptions: isAdminBuild ? { compatibility: { componentApi: 4 } } : {},
      }),
    ],
    build: {
      outDir: templateDir,
      emptyOutDir: false,
      minify: false,
      sourcemap: false,
      cssCodeSplit: false,
      lib: {
        entry: path.resolve(__dirname, isAdminBuild ? "src/adminEntry.js" : "src/main.js"),
        name: isAdminBuild ? "SubscriptionWebAppAdmin" : "SubscriptionWebApp",
        formats: ["iife"],
        fileName: () => `${outputBase}.js`,
        cssFileName: outputBase,
      },
      rolldownOptions: {
        checks: {
          pluginTimings: false,
        },
        output: {
          assetFileNames: (assetInfo) => {
            if (assetInfo.name && assetInfo.name.endsWith(".css")) {
              return `${outputBase}.css`;
            }
            return `${outputBase}.[name][extname]`;
          },
        },
      },
    },
  };
});

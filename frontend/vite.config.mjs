import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const templateDir = path.resolve(__dirname, "../backend/bot/app/web/templates");

export default defineConfig(({ command, mode }) => {
  const isAdminBuild = mode === "admin";
  const isDocsDemoBuild = mode === "docs-demo";
  const nodeEnv = command === "build" ? "production" : "development";
  const outputBase = isAdminBuild
    ? "subscription_webapp_admin"
    : isDocsDemoBuild
      ? "subscription_webapp_docs_demo"
      : "subscription_webapp";
  const entry = isAdminBuild
    ? "src/adminEntry.js"
    : isDocsDemoBuild
      ? "src/docsDemoEntry.js"
      : "src/main.js";

  return {
    define: {
      "process.env.NODE_ENV": JSON.stringify(nodeEnv),
    },
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
        entry: path.resolve(__dirname, entry),
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

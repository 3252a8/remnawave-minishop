import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";
import { accordionLifecycleFix } from "./scripts/vite-accordion-lifecycle.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(__dirname, "src");
const templateDir = path.resolve(__dirname, "../backend/bot/app/web/templates");

function firstPartyRunesOptions({ filename }) {
  if (filename && path.resolve(filename).startsWith(srcDir)) {
    return { runes: true };
  }
}

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
    ? "src/adminEntry.ts"
    : isDocsDemoBuild
      ? "src/docsDemoEntry.ts"
      : "src/main.ts";

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
      accordionLifecycleFix(),
      tailwindcss(),
      svelte({
        dynamicCompileOptions: firstPartyRunesOptions,
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
        // Every bundle ships as an ES module so a screen the customer has not
        // opened yet can stay in its own chunk. The shells load it with
        // `<script type="module">`.
        formats: ["es"],
        fileName: () => `${outputBase}.js`,
        cssFileName: outputBase,
      },
      rolldownOptions: {
        checks: {
          pluginTimings: false,
        },
        output: {
          // `[name]` comes from the chunk's entry module, so `foo.svelte.ts`
          // would put a second dot in the file name — and every consumer
          // (the aiohttp route, the nginx copy, the docs demo) matches chunk
          // names segment by segment. Flattening it here keeps one dot before
          // the hash no matter what a source file is called.
          chunkFileNames: (chunkInfo) =>
            `${outputBase}.${String(chunkInfo.name || "chunk").replace(/[^A-Za-z0-9_-]+/g, "-")}.[hash].js`,
          manualChunks: isAdminBuild
            ? (id) => {
                const normalizedId = id.split(path.sep).join("/");
                if (normalizedId.includes("/node_modules/uplot/")) {
                  return "admin-chart";
                }
                if (normalizedId.includes("/node_modules/")) {
                  return "admin-vendor";
                }
              }
            : (id) => {
                // The editor is only mounted on the support screens, and it is
                // the heaviest thing the customer app can pull in. Keeping its
                // dependencies together makes that one chunk cacheable instead
                // of smeared across every screen that lazily needs it.
                const normalizedId = id.split(path.sep).join("/");
                if (
                  normalizedId.includes("/node_modules/@tiptap/") ||
                  normalizedId.includes("/node_modules/prosemirror-") ||
                  normalizedId.includes("/node_modules/orderedmap/") ||
                  normalizedId.includes("/node_modules/w3c-keyname/") ||
                  normalizedId.includes("/node_modules/rope-sequence/")
                ) {
                  return "richtext";
                }
              },
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

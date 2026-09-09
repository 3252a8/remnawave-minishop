import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import tseslint from "typescript-eslint";
import uiReuse from "./scripts/eslint-ui-reuse.mjs";

/** @type {import("eslint").Linter.Config[]} */
export default [
  {
    ignores: ["**/node_modules/**", "../backend/bot/app/web/templates/**"],
  },
  js.configs.recommended,
  ...svelte.configs["flat/base"],
  {
    files: ["src/**/*.svelte"],
    rules: {
      "svelte/no-restricted-html-elements": [
        "error",
        {
          elements: ["select"],
          message:
            "Use AdminSelect or the shared Select pattern; native menus bypass the UI library.",
        },
      ],
    },
  },
  {
    files: ["src/**/*.svelte", "src/**/*.ts"],
    ignores: ["src/lib/components/ui/**", "src/**/*.test.ts", "src/**/*.spec.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["bits-ui", "bits-ui/*", "@lucide/*", "lucide-svelte"],
              message:
                "Import shared UI primitives/icons through $components/ui; reuse a higher-level pattern first.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/**/*.svelte"],
    ignores: ["src/lib/components/ui/**"],
    plugins: { "ui-reuse": uiReuse },
    rules: { "ui-reuse/native-controls": "error" },
  },
  {
    files: ["src/**/*.{js,ts,svelte}", "scripts/**/*.mjs"],
    rules: {
      "no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "no-empty": "warn",
    },
  },
  {
    files: ["src/**/*.svelte"],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
    },
    rules: {
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "no-useless-assignment": "off",
    },
  },
  {
    files: ["src/**/*.ts"],
    languageOptions: {
      parser: tseslint.parser,
    },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
    },
    rules: {
      "no-undef": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: ["src/**/*.{js,ts,svelte}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
      sourceType: "module",
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.es2021,
      },
      sourceType: "module",
    },
  },
  eslintConfigPrettier,
];

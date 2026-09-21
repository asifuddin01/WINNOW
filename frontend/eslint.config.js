import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "coverage",
      "public/theme-init.js",
      "src/routeTree.gen.ts",
      "src/api/schema.d.ts",
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      jsxA11y.flatConfigs.recommended,
      reactHooks.configs.flat["recommended-latest"],
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-refresh": reactRefresh },
    rules: {
      "react-refresh/only-export-components": ["error", { allowConstantExport: true }],
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      "no-restricted-syntax": [
        "error",
        {
          // Guide 12.3: only the keyword-highlight component may build markup, and
          // it builds nodes, not HTML strings.
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "dangerouslySetInnerHTML is forbidden (guide 12.3).",
        },
      ],
      "no-restricted-properties": [
        "error",
        {
          object: "localStorage",
          message: "Use readPreference/writePreference from @/lib/storage (UI preferences only).",
        },
        {
          object: "sessionStorage",
          message:
            "Do not persist data in sessionStorage; tokens and research data never go to web storage.",
        },
      ],
    },
  },
  {
    // shadcn/ui components are generated code we own; keep their upstream shape.
    files: ["src/components/ui/**"],
    rules: {
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-unnecessary-condition": "off",
      "@typescript-eslint/consistent-type-definitions": "off",
      "@typescript-eslint/no-confusing-void-expression": "off",
    },
  },
  {
    // Route files export `Route`; the router plugin splits their components and handles HMR.
    files: ["src/routes/**"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    files: ["src/lib/storage.ts"],
    rules: { "no-restricted-properties": "off" },
  },
  {
    files: ["vite.config.ts", "eslint.config.js", "scripts/**"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["**/*.js", "**/*.mjs"],
    extends: [tseslint.configs.disableTypeChecked],
  },
);

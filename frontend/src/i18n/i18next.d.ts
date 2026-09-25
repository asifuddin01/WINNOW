import "i18next";

import type common from "@/i18n/locales/en/common.json";

// Keys are checked by TypeScript: a misspelt or missing one does not compile.
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: { common: typeof common };
  }
}

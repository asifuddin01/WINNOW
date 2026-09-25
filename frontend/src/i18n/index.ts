/**
 * Every string in the interface comes from a catalogue (guide 14): English first, laid out
 * so another language (Bangla, বাংলা, is the first planned) is a folder of JSON files and a
 * line in LANGUAGES. Numbers and dates go through `Intl`, in the chosen language.
 *
 * The English catalogue is bundled (it is the fallback, needed before anything renders);
 * other languages would be loaded when chosen. docs/i18n.md says what is translated yet.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import common from "@/i18n/locales/en/common.json";

export const LANGUAGES = { en: "English" } as const;
export type Language = keyof typeof LANGUAGES;
export const defaultNS = "common";
export const resources = { en: { common } } as const;

/** The first of the browser's preferred languages Winnow speaks, else English. */
export function preferredLanguage(wanted: readonly string[] = navigator.languages): Language {
  for (const tag of wanted) {
    const base = tag.toLowerCase().split("-")[0];
    if (base && base in LANGUAGES) return base as Language;
  }
  return "en";
}

void i18n.use(initReactI18next).init({
  resources,
  lng: preferredLanguage(),
  fallbackLng: "en",
  defaultNS,
  ns: [defaultNS],
  // React escapes what it renders; escaping here as well would show "&amp;".
  interpolation: { escapeValue: false },
  initAsync: false,
});
document.documentElement.lang = i18n.language;

export default i18n;

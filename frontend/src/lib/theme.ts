import { createContext, useContext } from "react";

import { readPreference } from "@/lib/storage";

export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];
export type ResolvedTheme = Exclude<Theme, "system">;

/** Must match public/theme-init.js, which applies the theme before React loads. */
export const THEME_STORAGE_KEY = "winnow-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function isTheme(value: unknown): value is Theme {
  return THEMES.includes(value as Theme);
}

export function storedTheme(): Theme {
  const saved = readPreference(THEME_STORAGE_KEY);
  return isTheme(saved) ? saved : "system";
}

export function systemTheme(): ResolvedTheme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === "system" ? systemTheme() : theme;
}

export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

export function watchSystemTheme(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => {
    query.removeEventListener("change", onChange);
  };
}

export interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside <ThemeProvider>");
  return context;
}

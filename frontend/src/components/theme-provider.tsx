import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { writePreference } from "@/lib/storage";
import {
  THEME_STORAGE_KEY,
  ThemeContext,
  applyTheme,
  resolveTheme,
  storedTheme,
  watchSystemTheme,
  type ResolvedTheme,
  type Theme,
} from "@/lib/theme";

/** Light, dark, or follow the system (the default), per guide 11.3. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(storedTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolveTheme(theme));

  useEffect(() => {
    const update = () => {
      const resolved = resolveTheme(theme);
      setResolvedTheme(resolved);
      applyTheme(resolved);
    };
    update();
    return theme === "system" ? watchSystemTheme(update) : undefined;
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    writePreference(THEME_STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

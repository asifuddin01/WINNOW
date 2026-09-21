/**
 * localStorage for UI preferences only (theme, sidebar). Never tokens or research
 * data (CLAUDE.md). Storage can be unavailable (private mode, blocked site data),
 * so every access is guarded and the app works without it.
 */
export function readPreference(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Preference simply is not remembered.
  }
}

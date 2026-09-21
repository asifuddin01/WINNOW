/** jsdom has no matchMedia. This fake answers the two queries the app asks. */
interface MediaState {
  dark: boolean;
  mobile: boolean;
}

const state: MediaState = { dark: false, mobile: false };
const listeners = new Set<{ query: string; listener: () => void }>();

function matches(query: string): boolean {
  if (query.includes("prefers-color-scheme: dark")) return state.dark;
  if (query.includes("max-width")) return state.mobile;
  return false;
}

export function installMatchMedia(initial: Partial<MediaState> = {}): void {
  Object.assign(state, { dark: false, mobile: false }, initial);
  listeners.clear();
  window.matchMedia = (query: string) =>
    ({
      get matches() {
        return matches(query);
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: () => void) => {
        listeners.add({ query, listener });
      },
      removeEventListener: (_type: string, listener: () => void) => {
        for (const entry of listeners) if (entry.listener === listener) listeners.delete(entry);
      },
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

/** Change the fake system preference and notify listeners, as the browser would. */
export function setMedia(next: Partial<MediaState>): void {
  Object.assign(state, next);
  for (const { listener } of listeners) listener();
}

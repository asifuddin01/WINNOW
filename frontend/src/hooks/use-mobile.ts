import { useSyncExternalStore } from "react";

const MOBILE_BREAKPOINT = 768;
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;

function subscribe(onChange: () => void) {
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener("change", onChange);
  return () => {
    query.removeEventListener("change", onChange);
  };
}

/** True below the tablet breakpoint, correct from the first render (no layout flash). */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(MOBILE_QUERY).matches);
}

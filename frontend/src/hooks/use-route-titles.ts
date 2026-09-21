import { useMatches } from "@tanstack/react-router";

declare module "@tanstack/react-router" {
  interface StaticDataRouteOption {
    /** Human title shown in breadcrumbs and the browser tab. */
    title?: string;
  }
}

/** Titles of the matched routes, outermost first. */
export function useRouteTitles(): string[] {
  const matches = useMatches();
  return matches.flatMap((match) => (match.staticData.title ? [match.staticData.title] : []));
}

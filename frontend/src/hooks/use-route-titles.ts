import { useMatches } from "@tanstack/react-router";

declare module "@tanstack/react-router" {
  interface StaticDataRouteOption {
    /** Human title shown in breadcrumbs and the browser tab. */
    title?: string;
    /** A crumb whose text is loaded, not fixed: today, a review's title. */
    crumb?: "project";
  }
}

export interface Crumb {
  key: string;
  /** Fixed text, or undefined when the crumb reads its text from loaded data. */
  title?: string;
  /** Set for the review crumb: the id whose title to show. */
  projectId?: string;
}

/** Crumbs for the matched routes, outermost first. */
export function useCrumbs(): Crumb[] {
  const matches = useMatches();
  return matches.flatMap<Crumb>((match): Crumb[] => {
    if (match.staticData.crumb === "project") {
      const params = match.params as { pid?: string };
      return params.pid ? [{ key: match.routeId, projectId: params.pid }] : [];
    }
    return match.staticData.title ? [{ key: match.routeId, title: match.staticData.title }] : [];
  });
}

/** The fixed titles among the crumbs; the browser tab uses the last of them. */
export function useRouteTitles(): string[] {
  return useCrumbs().flatMap((crumb) => (crumb.title ? [crumb.title] : []));
}

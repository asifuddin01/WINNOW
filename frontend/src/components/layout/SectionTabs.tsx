import { Link } from "@tanstack/react-router";

import type { FileRouteTypes } from "@/routeTree.gen";
import { cn } from "@/lib/utils";

export interface SectionTab {
  to: FileRouteTypes["to"];
  label: string;
  exact?: boolean;
}

/** The sub-pages of a review's section, as links (each has its own address). */
export function SectionTabs({
  pid,
  label,
  tabs,
}: {
  /** The review the tabs belong to; none for instance pages such as /admin. */
  pid?: string;
  label: string;
  tabs: SectionTab[];
}) {
  return (
    <nav aria-label={label} className="border-b border-border">
      <ul className="-mb-px flex flex-wrap gap-1">
        {tabs.map((tab) => (
          <li key={tab.to}>
            <Link
              to={tab.to}
              params={pid ? { pid } : {}}
              activeOptions={{ exact: tab.exact ?? false }}
              className={cn(
                "inline-block border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
                "focus-visible:rounded-t-md focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
              )}
              activeProps={{
                className: "border-primary font-medium text-foreground",
                "aria-current": "page",
              }}
            >
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

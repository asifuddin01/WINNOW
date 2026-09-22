import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import type { FileRouteTypes } from "@/routeTree.gen";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/settings")({
  component: SettingsLayout,
  staticData: { title: "Settings" },
});

const TABS: { to: FileRouteTypes["to"]; label: string; exact?: boolean }[] = [
  { to: "/p/$pid/settings", label: "General", exact: true },
  { to: "/p/$pid/settings/criteria", label: "Criteria" },
  { to: "/p/$pid/settings/keywords", label: "Keywords" },
  { to: "/p/$pid/settings/reasons", label: "Exclusion reasons" },
  { to: "/p/$pid/settings/labels", label: "Labels" },
  { to: "/p/$pid/settings/screening", label: "Screening" },
  { to: "/p/$pid/settings/team", label: "Team" },
];

function SettingsLayout() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">
          {project?.permissions.includes("edit_setup")
            ? "How this review works, and who works on it."
            : "How this review works. Your role lets you read these, not change them."}
        </p>
      </div>
      <nav aria-label="Settings sections" className="border-b border-border">
        <ul className="-mb-px flex flex-wrap gap-1">
          {TABS.map((tab) => (
            <li key={tab.to}>
              <Link
                to={tab.to}
                params={{ pid }}
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
      <Outlet />
    </div>
  );
}

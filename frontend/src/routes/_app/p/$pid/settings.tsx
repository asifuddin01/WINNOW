import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { SectionTabs, type SectionTab } from "@/components/layout/SectionTabs";

export const Route = createFileRoute("/_app/p/$pid/settings")({
  component: SettingsLayout,
  staticData: { title: "Settings" },
});

const TABS: SectionTab[] = [
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
      <SectionTabs pid={pid} label="Settings sections" tabs={TABS} />
      <Outlet />
    </div>
  );
}

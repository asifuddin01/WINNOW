import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { SectionTabs, type SectionTab } from "@/components/layout/SectionTabs";

export const Route = createFileRoute("/_app/p/$pid/report")({
  component: ReportLayout,
  staticData: { title: "Report" },
});

function ReportLayout() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  const tabs: SectionTab[] = [
    { to: "/p/$pid/report", label: "PRISMA", exact: true },
    { to: "/p/$pid/report/stats", label: "Statistics" },
    { to: "/p/$pid/report/methods", label: "Methods text" },
    { to: "/p/$pid/report/exports", label: "Exports" },
    // The log holds people's addresses: owners and admins only (guide 12.8).
    ...(project?.permissions.includes("edit_settings")
      ? [{ to: "/p/$pid/report/audit", label: "Audit log" } as const]
      : []),
  ];

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Report</h1>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          What the review found and how it was done: the PRISMA 2020 flow, screening statistics, and
          the files to take elsewhere.
        </p>
      </div>
      <SectionTabs pid={pid} label="Report sections" tabs={tabs} />
      <Outlet />
    </div>
  );
}

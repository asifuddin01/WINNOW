import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { SectionTabs, type SectionTab } from "@/components/layout/SectionTabs";

export const Route = createFileRoute("/_app/p/$pid/extraction")({
  component: ExtractionLayout,
  staticData: { title: "Extraction" },
});

function ExtractionLayout() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  const tabs: SectionTab[] = [
    { to: "/p/$pid/extraction", label: "Extract", exact: true },
    { to: "/p/$pid/extraction/forms", label: "Forms" },
    ...(project?.permissions.includes("resolve_conflicts")
      ? [{ to: "/p/$pid/extraction/consensus", label: "Consensus" } as const]
      : []),
  ];
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Data extraction</h1>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          Each study included at full text is extracted with a published form, by each reviewer on
          their own. With two extractors, someone who resolves conflicts reconciles them.
        </p>
      </div>
      <SectionTabs pid={pid} label="Extraction sections" tabs={tabs} />
      <Outlet />
    </div>
  );
}

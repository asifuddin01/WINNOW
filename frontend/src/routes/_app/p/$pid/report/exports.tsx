import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { ExportsView } from "@/features/report/ExportsView";

export const Route = createFileRoute("/_app/p/$pid/report/exports")({
  component: ExportsPage,
  staticData: { title: "Exports" },
});

function ExportsPage() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return <ExportsView pid={pid} isOwner={project.membership.role === "owner"} />;
}

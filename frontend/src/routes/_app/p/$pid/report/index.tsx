import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { PrismaView } from "@/features/report/PrismaView";

export const Route = createFileRoute("/_app/p/$pid/report/")({
  component: PrismaPage,
  staticData: { title: "PRISMA" },
});

function PrismaPage() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return <PrismaView pid={pid} canEdit={project.permissions.includes("edit_settings")} />;
}

import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { ReasonsEditor } from "@/features/projects/ReasonsEditor";

export const Route = createFileRoute("/_app/p/$pid/settings/reasons")({
  component: ReasonSettings,
  staticData: { title: "Exclusion reasons" },
});

function ReasonSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return (
    <Section
      title="Exclusion reasons"
      description="Reviewers choose from these when they exclude a record. PRISMA 2020 reports the full-text ones."
    >
      <ReasonsEditor pid={pid} canEdit={project.permissions.includes("edit_setup")} />
    </Section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { CriteriaEditor } from "@/features/projects/CriteriaEditor";

export const Route = createFileRoute("/_app/p/$pid/settings/criteria")({
  component: CriteriaSettings,
  staticData: { title: "Criteria" },
});

function CriteriaSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return (
    <Section
      title="Screening criteria"
      description="Reviewers see these beside every record. Keep each one short and testable."
    >
      <CriteriaEditor pid={pid} canEdit={project.permissions.includes("edit_setup")} />
    </Section>
  );
}

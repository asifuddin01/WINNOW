import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { LabelsEditor } from "@/features/projects/LabelsEditor";

export const Route = createFileRoute("/_app/p/$pid/settings/labels")({
  component: LabelSettings,
  staticData: { title: "Labels" },
});

function LabelSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return (
    <Section
      title="Labels"
      description="Tags for records, for anything the criteria do not cover. Reviewers can filter by them."
    >
      <LabelsEditor pid={pid} canEdit={project.permissions.includes("edit_setup")} />
    </Section>
  );
}

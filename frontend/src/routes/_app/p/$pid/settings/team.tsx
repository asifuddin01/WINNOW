import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { TeamEditor } from "@/features/projects/TeamEditor";

export const Route = createFileRoute("/_app/p/$pid/settings/team")({
  component: TeamSettings,
  staticData: { title: "Team" },
});

function TeamSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return (
    <Section
      title="Team"
      description={
        project.permissions.includes("manage_members")
          ? "Invite people, and set what each of them may do."
          : "Who is working on this review."
      }
    >
      <TeamEditor project={project} />
    </Section>
  );
}

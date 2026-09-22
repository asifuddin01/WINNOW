import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { KeywordsEditor } from "@/features/projects/KeywordsEditor";

export const Route = createFileRoute("/_app/p/$pid/settings/keywords")({
  component: KeywordSettings,
  staticData: { title: "Keywords" },
});

function KeywordSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  return (
    <Section
      title="Keyword groups"
      description="Terms worth spotting in a title or abstract. Each group is highlighted in its own colour while screening."
    >
      <KeywordsEditor pid={pid} canEdit={project.permissions.includes("edit_setup")} />
    </Section>
  );
}

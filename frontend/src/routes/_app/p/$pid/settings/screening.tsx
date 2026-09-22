import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { Section } from "@/features/account/Section";
import { MyScreeningPreferences } from "@/features/projects/MyScreeningPreferences";
import { ScreeningSettings } from "@/features/projects/ScreeningSettings";

export const Route = createFileRoute("/_app/p/$pid/settings/screening")({
  component: ScreeningSettingsPage,
  staticData: { title: "Screening" },
});

function ScreeningSettingsPage() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  if (!project.permissions.includes("edit_settings")) {
    return (
      <Section title="How screening runs" description="Only owners and admins change these.">
        <dl className="grid gap-2 text-sm sm:grid-cols-[16rem_1fr]">
          <dt className="text-muted-foreground">Blind screening</dt>
          <dd>{project.settings.blind_mode ? "On" : "Off"}</dd>
          <dt className="text-muted-foreground">Reviewers per record</dt>
          <dd>
            {project.settings.reviewers_per_record_ta} at title and abstract,{" "}
            {project.settings.reviewers_per_record_ft} at full text
          </dd>
        </dl>
      </Section>
    );
  }
  return (
    <div className="grid gap-6">
      <Section title="How screening runs" description="These apply to everyone on the review.">
        <ScreeningSettings project={project} />
      </Section>
      <MyScreeningPreferences project={project} />
    </div>
  );
}

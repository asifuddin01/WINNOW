import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { CopyPlusIcon } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import { duplicateSetup, projectKeys, projectQuery, updateProject } from "@/api/projects";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { Section } from "@/features/account/Section";
import { toProject, valuesFor } from "@/features/projects/basics";
import { BasicsForm } from "@/features/projects/BasicsForm";
import { DangerZone } from "@/features/projects/DangerZone";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

export const Route = createFileRoute("/_app/p/$pid/settings/")({
  component: GeneralSettings,
  staticData: { title: "General" },
});

function GeneralSettings() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  const save = useProjectMutation(
    (body: Parameters<typeof updateProject>[1]) => updateProject(pid, body),
    { invalidate: [projectKeys.detail(pid), projectKeys.list], success: "Review updated." },
  );
  if (!project) return null;
  const canEdit = project.permissions.includes("edit_settings");

  return (
    <div className="grid gap-6">
      <Section title="The review" description="Title, type and question.">
        {canEdit ? (
          <BasicsForm
            defaultValues={valuesFor(project)}
            submitLabel="Save changes"
            pending={save.isPending}
            problem={save.isError ? errorMessage(save.error) : null}
            onSubmit={(values) => {
              save.mutate(toProject(values));
            }}
          />
        ) : (
          <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted-foreground">Title</dt>
            <dd>{project.title}</dd>
            {project.research_question && (
              <>
                <dt className="text-muted-foreground">Question</dt>
                <dd>{project.research_question}</dd>
              </>
            )}
            {project.description && (
              <>
                <dt className="text-muted-foreground">Description</dt>
                <dd>{project.description}</dd>
              </>
            )}
          </dl>
        )}
      </Section>

      <CopySetup pid={pid} title={project.title} />

      <DangerZone project={project} />
    </div>
  );
}

/** Guide 8.2: reuse this review's setup as a template for the next one. */
function CopySetup({ pid, title }: { pid: string; title: string }) {
  const navigate = useNavigate();
  const [name, setName] = useState(`Copy of ${title}`);
  const copy = useProjectMutation(() => duplicateSetup(pid, name.trim()), {
    invalidate: [projectKeys.list],
    success: "New review created from this setup.",
  });

  return (
    <Section
      title="Start another review from this setup"
      description="Copies the settings, criteria, keywords, exclusion reasons and labels into a new review that you own. Records, decisions and members are not copied."
    >
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          copy.mutate(undefined, {
            onSuccess: (project) => void navigate({ to: "/p/$pid", params: { pid: project.id } }),
          });
        }}
      >
        <div className="min-w-60 flex-1">
          <TextField
            label="Title of the copy"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </div>
        <Button type="submit" variant="outline" disabled={copy.isPending}>
          <CopyPlusIcon aria-hidden="true" /> Copy setup
        </Button>
      </form>
    </Section>
  );
}

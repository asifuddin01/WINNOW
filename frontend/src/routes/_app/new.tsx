import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { CheckIcon } from "lucide-react";

import { createProject, projectKeys, projectQuery } from "@/api/projects";
import { errorMessage } from "@/api/client";
import { Button } from "@/components/ui/button";
import { toProject, valuesFor } from "@/features/projects/basics";
import { BasicsForm } from "@/features/projects/BasicsForm";
import { CriteriaEditor } from "@/features/projects/CriteriaEditor";
import { KeywordsEditor } from "@/features/projects/KeywordsEditor";
import { ReasonsEditor } from "@/features/projects/ReasonsEditor";
import { TeamEditor } from "@/features/projects/TeamEditor";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { wizardSearch, type WizardStep } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/new")({
  validateSearch: wizardSearch,
  component: NewReview,
  staticData: { title: "New review" },
});

const STEPS: { key: WizardStep; label: string }[] = [
  { key: "basics", label: "Basics" },
  { key: "criteria", label: "Criteria and keywords" },
  { key: "team", label: "Team" },
];

/**
 * Three steps (guide 8.2). The review is created at the end of step one, so nothing
 * typed afterwards is lost if the tab closes: the rest is ordinary editing, with the
 * same editors as the settings pages.
 */
function NewReview() {
  const { project: pid, step } = Route.useSearch();
  const current: WizardStep = pid ? (step ?? "criteria") : "basics";

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New review</h1>
        <p className="mt-1 text-muted-foreground">
          Three steps, and none of them is final: everything here can change later in settings.
        </p>
      </div>
      <ol className="flex flex-wrap gap-2" aria-label="Steps">
        {STEPS.map((item, index) => {
          const done = STEPS.findIndex((s) => s.key === current) > index;
          const active = item.key === current;
          return (
            <li
              key={item.key}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-sm",
                active
                  ? "border-primary/40 bg-primary/10 font-medium text-primary"
                  : "border-border text-muted-foreground",
              )}
            >
              {done ? (
                <CheckIcon className="size-3.5" aria-hidden="true" />
              ) : (
                <span aria-hidden="true">{index + 1}.</span>
              )}
              {item.label}
              {done && <span className="sr-only">(done)</span>}
            </li>
          );
        })}
      </ol>
      {current === "basics" || !pid ? <Basics /> : <Setup pid={pid} step={current} />}
    </div>
  );
}

function Basics() {
  const navigate = useNavigate();
  const create = useProjectMutation(createProject, { invalidate: [projectKeys.list] });
  return (
    <BasicsForm
      defaultValues={valuesFor(undefined)}
      submitLabel="Continue"
      pending={create.isPending}
      problem={create.isError ? errorMessage(create.error) : null}
      onSubmit={(values) => {
        create.mutate(toProject(values), {
          onSuccess: (project) =>
            void navigate({ to: "/new", search: { project: project.id, step: "criteria" } }),
        });
      }}
    />
  );
}

function Setup({ pid, step }: { pid: string; step: WizardStep }) {
  const navigate = useNavigate();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;

  if (step === "team") {
    return (
      <div className="grid gap-6">
        <section aria-labelledby="team" className="grid gap-4">
          <div>
            <h2 id="team" className="text-lg font-medium">
              Who is working on {project.title}?
            </h2>
            <p className="text-sm text-muted-foreground">
              Invite people by email. They join as soon as they accept; you can change roles later.
            </p>
          </div>
          <TeamEditor project={project} />
        </section>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => void navigate({ to: "/p/$pid", params: { pid } })}>
            Finish and open the review
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              void navigate({ to: "/new", search: { project: pid, step: "criteria" } })
            }
          >
            Back
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-8">
      <section aria-labelledby="criteria" className="grid gap-4">
        <div>
          <h2 id="criteria" className="text-lg font-medium">
            What counts as relevant?
          </h2>
          <p className="text-sm text-muted-foreground">
            Criteria are the rules reviewers screen against; they appear beside every record.
          </p>
        </div>
        <CriteriaEditor pid={pid} canEdit />
      </section>
      <section aria-labelledby="keywords" className="grid gap-4">
        <div>
          <h2 id="keywords" className="text-lg font-medium">
            Keywords to highlight
          </h2>
          <p className="text-sm text-muted-foreground">
            Optional. Terms in a group are highlighted in one colour while screening.
          </p>
        </div>
        <KeywordsEditor pid={pid} canEdit />
      </section>
      <section aria-labelledby="reasons" className="grid gap-4">
        <div>
          <h2 id="reasons" className="text-lg font-medium">
            Exclusion reasons
          </h2>
          <p className="text-sm text-muted-foreground">
            The usual reasons are ready to use. Add your own, or remove what you do not need.
          </p>
        </div>
        <ReasonsEditor pid={pid} canEdit />
      </section>
      <div className="flex flex-wrap gap-3">
        <Button
          onClick={() => void navigate({ to: "/new", search: { project: pid, step: "team" } })}
        >
          Continue to the team
        </Button>
        <Button variant="ghost" onClick={() => void navigate({ to: "/p/$pid", params: { pid } })}>
          Skip for now
        </Button>
      </div>
    </div>
  );
}

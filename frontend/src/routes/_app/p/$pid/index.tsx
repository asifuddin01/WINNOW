import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { CheckIcon, CircleDashedIcon, SettingsIcon, UsersIcon } from "lucide-react";

import { criteriaQuery, keywordGroupsQuery, membersQuery, projectQuery } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Section } from "@/features/account/Section";
import { COLOR_DOT } from "@/features/projects/palette";
import { CRITERION_KINDS, REVIEW_TYPES, ROLES, STATUSES } from "@/features/projects/wording";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/")({
  component: Overview,
  staticData: { title: "Overview" },
});

function Overview() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  const { data: criteria = [] } = useQuery(criteriaQuery(pid));
  const { data: groups = [] } = useQuery(keywordGroupsQuery(pid));
  const { data: members } = useQuery(membersQuery(pid));
  if (!project) return null;

  const team = members?.items ?? [];
  const canEdit = project.permissions.includes("edit_setup");
  const checklist = [
    { done: criteria.length > 0, label: "Screening criteria", to: "/p/$pid/settings/criteria" },
    { done: groups.length > 0, label: "Keywords to highlight", to: "/p/$pid/settings/keywords" },
    { done: team.length > 1, label: "Reviewers invited", to: "/p/$pid/settings/team" },
  ] as const;

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-muted-foreground">
            {REVIEW_TYPES[project.review_type]}
            <Badge variant="outline">{STATUSES[project.status]}</Badge>
            <Badge variant="secondary">You are {ROLES[project.membership.role]}</Badge>
          </p>
        </div>
        <Button asChild variant="outline">
          <Link to="/p/$pid/settings" params={{ pid }}>
            <SettingsIcon aria-hidden="true" /> Settings
          </Link>
        </Button>
      </div>

      {project.description && <p className="max-w-[75ch]">{project.description}</p>}

      <Section
        title="Getting ready"
        description="Records and screening arrive once your search results are imported."
      >
        <ul className="grid gap-2">
          {checklist.map((item) => (
            <li key={item.label} className="flex items-center gap-2 text-sm">
              {item.done ? (
                <CheckIcon
                  className="size-4 text-green-600 dark:text-green-400"
                  aria-hidden="true"
                />
              ) : (
                <CircleDashedIcon className="size-4 text-muted-foreground" aria-hidden="true" />
              )}
              <span className={item.done ? "" : "text-muted-foreground"}>{item.label}</span>
              <span className="sr-only">{item.done ? "done" : "still to do"}</span>
              {canEdit && !item.done && (
                <Link
                  to={item.to}
                  params={{ pid }}
                  className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                >
                  Set up
                </Link>
              )}
            </li>
          ))}
        </ul>
      </Section>

      {(project.research_question ?? project.pico) && (
        <Section title="The question">
          {project.research_question && <p className="max-w-[75ch]">{project.research_question}</p>}
          {project.pico && (
            <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-[8rem_1fr]">
              {(
                [
                  ["Population", project.pico.population],
                  ["Intervention", project.pico.intervention],
                  ["Comparator", project.pico.comparator],
                  ["Outcome", project.pico.outcome],
                ] as const
              )
                .filter(([, value]) => value)
                .map(([label, value]) => (
                  <div key={label} className="contents">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
            </dl>
          )}
        </Section>
      )}

      <Section
        title="Criteria"
        aside={
          canEdit ? (
            <Button asChild variant="ghost" size="sm">
              <Link to="/p/$pid/settings/criteria" params={{ pid }}>
                Edit
              </Link>
            </Button>
          ) : undefined
        }
      >
        {criteria.length === 0 ? (
          <p className="text-sm text-muted-foreground">No criteria yet.</p>
        ) : (
          <ul className="grid gap-2 text-sm">
            {criteria.map((criterion) => (
              <li key={criterion.id} className="flex items-start gap-2">
                <Badge variant={criterion.kind === "inclusion" ? "secondary" : "outline"}>
                  {CRITERION_KINDS[criterion.kind]}
                </Badge>
                <span>{criterion.text}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {groups.length > 0 && (
        <Section title="Keyword groups">
          <ul className="flex flex-wrap gap-2 text-sm">
            {groups.map((group) => (
              <li key={group.id} className="flex items-center gap-2 rounded-full border px-3 py-1">
                <span
                  className={cn("size-2 rounded-full", COLOR_DOT[group.color])}
                  aria-hidden="true"
                />
                {group.name}
                <span className="text-muted-foreground">
                  {group.keywords.length} {group.keywords.length === 1 ? "term" : "terms"}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section
        title="Team"
        description={`${project.member_count} ${project.member_count === 1 ? "person" : "people"} on this review.`}
        aside={
          <Button asChild variant="ghost" size="sm">
            <Link to="/p/$pid/settings/team" params={{ pid }}>
              <UsersIcon aria-hidden="true" /> Manage
            </Link>
          </Button>
        }
      >
        <ul className="flex flex-wrap gap-2">
          {team.map((member) => (
            <li
              key={member.user.id}
              className="flex items-center gap-2 rounded-full border border-border py-1 pr-3 pl-1 text-sm"
            >
              <span
                aria-hidden="true"
                className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground"
              >
                {initials(member.user.name)}
              </span>
              {member.user.name}
              <span className="text-xs text-muted-foreground">{ROLES[member.role]}</span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

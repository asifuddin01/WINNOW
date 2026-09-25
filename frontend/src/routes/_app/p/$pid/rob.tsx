import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeftIcon, DownloadIcon, ExternalLinkIcon, GaugeIcon } from "lucide-react";

import { projectQuery } from "@/api/projects";
import {
  recordRobQuery,
  robPlotUrl,
  robStudiesQuery,
  robSummaryQuery,
  robToolsQuery,
  type RobSummary,
  type RobTool,
  type StudyStatus,
} from "@/api/rob";
import { SelectField } from "@/components/forms/SelectField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AssessmentForm, OtherAssessments } from "@/features/rob/AssessmentForm";
import { JudgementMark } from "@/features/rob/JudgementMark";
import { robSearch, type RobToolKey } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/rob")({
  validateSearch: robSearch,
  component: RiskOfBias,
  staticData: { title: "Risk of bias" },
});

function RiskOfBias() {
  const { pid } = Route.useParams();
  const { tool: toolKey = "rob2", study } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: project } = useQuery(projectQuery(pid));
  const { data: tools } = useQuery(robToolsQuery(pid));
  const { data: studies, isPending } = useQuery(robStudiesQuery(pid, toolKey));
  const tool = tools?.find((t) => t.key === toolKey);

  if (!project) return null;
  const canAssess = project.permissions.includes("screen");

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Risk of bias</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            Each study included at full text is assessed on its own by each reviewer, blinded like
            screening. The review&apos;s plots use one final assessment per study.
          </p>
        </div>
        {tools && (
          <div className="w-full max-w-64">
            <SelectField
              label="Tool"
              value={toolKey}
              options={tools.map((t) => ({ value: t.key as RobToolKey, label: t.name }))}
              onChange={(next) => {
                void navigate({ search: { tool: next, study } });
              }}
            />
          </div>
        )}
      </div>

      {tool && (
        <p className="-mt-3 text-xs text-muted-foreground">
          {tool.name}, {tool.version}.{" "}
          <a
            href={tool.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 underline underline-offset-2"
          >
            The tool&apos;s guidance <ExternalLinkIcon className="size-3" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <StudyList
          pid={pid}
          toolKey={toolKey}
          studies={studies}
          loading={isPending}
          selected={study}
        />
        <div className="min-w-0">
          {!tool ? (
            <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />
          ) : study ? (
            <Study
              pid={pid}
              rid={study}
              tool={tool}
              canAssess={canAssess}
              canChoose={project.permissions.includes("resolve_conflicts")}
            />
          ) : (
            <Summary pid={pid} tool={tool} hasStudies={(studies?.length ?? 0) > 0} />
          )}
        </div>
      </div>
    </div>
  );
}

const MINE: Record<StudyStatus["mine"], string> = {
  none: "Not started",
  draft: "Draft",
  submitted: "Submitted",
};

function StudyList({
  pid,
  toolKey,
  studies,
  loading,
  selected,
}: {
  pid: string;
  toolKey: RobToolKey;
  studies: StudyStatus[] | undefined;
  loading: boolean;
  selected: string | undefined;
}) {
  if (loading) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (!studies || studies.length === 0) {
    return (
      <p className="grid justify-items-center gap-2 rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
        <GaugeIcon className="size-6" aria-hidden="true" />
        No studies yet. Studies appear here once they are included at full text.
      </p>
    );
  }
  const done = studies.filter((s) => s.mine === "submitted").length;
  return (
    <nav aria-label="Studies" className="grid content-start gap-2">
      <p className="text-sm text-muted-foreground">
        You have submitted {done} of {studies.length}.
      </p>
      <ul className="grid gap-1">
        {studies.map((item) => (
          <li key={item.record_id}>
            <Link
              to="/p/$pid/rob"
              params={{ pid }}
              search={{ tool: toolKey, study: item.record_id }}
              aria-current={selected === item.record_id ? "page" : undefined}
              className={cn(
                "grid gap-0.5 rounded-lg border border-transparent px-3 py-2 text-sm hover:bg-muted",
                "focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                selected === item.record_id && "border-border bg-muted",
              )}
            >
              <span className="font-medium">{item.label}</span>
              <span className="line-clamp-1 text-xs text-muted-foreground">{item.title}</span>
              <span className="flex flex-wrap gap-1 pt-0.5">
                <Badge variant={item.mine === "submitted" ? "default" : "secondary"}>
                  {MINE[item.mine]}
                </Badge>
                {item.submitted !== null && item.submitted > 1 && (
                  <Badge variant={item.final_chosen ? "outline" : "destructive"}>
                    {item.final_chosen ? "Final chosen" : `${item.submitted} to reconcile`}
                  </Badge>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Study({
  pid,
  rid,
  tool,
  canAssess,
  canChoose,
}: {
  pid: string;
  rid: string;
  tool: RobTool;
  canAssess: boolean;
  canChoose: boolean;
}) {
  const { data, error, isPending } = useQuery(recordRobQuery(pid, rid));
  const back = (
    <Button asChild variant="ghost" size="sm" className="justify-self-start">
      <Link to="/p/$pid/rob" params={{ pid }} search={{ tool: tool.key as RobToolKey }}>
        <ArrowLeftIcon aria-hidden="true" /> Summary
      </Link>
    </Button>
  );
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />;
  if (error) {
    return (
      <div className="grid gap-3">
        {back}
        <p className="text-sm text-muted-foreground">
          This study cannot be assessed: it is not included at full text.
        </p>
      </div>
    );
  }
  const forTool = data.assessments.filter((a) => a.tool_key === tool.key);
  const mine = forTool.find((a) => a.mine);
  return (
    <div className="grid gap-5">
      {back}
      <h2 className="text-lg font-medium">{data.title ?? "Untitled record"}</h2>
      <AssessmentForm
        key={`${rid}:${tool.key}:${mine?.updated_at ?? "new"}`}
        pid={pid}
        rid={rid}
        tool={tool}
        mine={mine}
        canAssess={canAssess}
      />
      <OtherAssessments
        pid={pid}
        rid={rid}
        tool={tool}
        others={forTool.filter((a) => !a.mine)}
        canChoose={canChoose}
      />
    </div>
  );
}

function Summary({ pid, tool, hasStudies }: { pid: string; tool: RobTool; hasStudies: boolean }) {
  const { data: summary, dataUpdatedAt } = useQuery(robSummaryQuery(pid, tool.key));
  if (!hasStudies) return null;
  if (!summary) return <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />;
  const shown = summary.variants.filter((variant) => variant.studies.length > 0);
  return (
    <div className="grid gap-5">
      {summary.own_only && (
        <p className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
          Blind mode is on: these plots show your own assessments only.
        </p>
      )}
      {summary.awaiting_final.length > 0 && (
        <p className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
          {summary.awaiting_final.length}{" "}
          {summary.awaiting_final.length === 1 ? "study was" : "studies were"} assessed by more than
          one person and {summary.awaiting_final.length === 1 ? "waits" : "wait"} for a final
          assessment before {summary.awaiting_final.length === 1 ? "it appears" : "they appear"} in
          the plots.
        </p>
      )}
      {shown.length === 0 ? (
        <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
          No submitted assessments with {tool.name} yet. Open a study to assess it.
        </p>
      ) : (
        shown.map((variant) => (
          <section
            key={variant.variant_key}
            className="grid min-w-0 gap-4"
            aria-label={variant.variant_name}
          >
            {summary.variants.length > 1 && (
              <h2 className="text-lg font-medium">{variant.variant_name}</h2>
            )}
            {(["traffic-light", "summary"] as const).map((plot) => (
              <figure key={plot} className="grid min-w-0 gap-2">
                {/* Wide plots scroll sideways; the box takes focus so the keyboard can too. */}
                {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- a scrollable region has to be
                    keyboard reachable (axe scrollable-region-focusable), which this rule forbids. */}
                <div
                  tabIndex={0}
                  role="region"
                  aria-label={plot === "traffic-light" ? "Traffic-light plot" : "Summary plot"}
                  className="overflow-x-auto rounded-xl border border-border bg-white dark:brightness-90 p-3 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
                  <img
                    src={`${robPlotUrl(pid, tool.key, { plot, variant: variant.variant_key, inline: true })}&v=${dataUpdatedAt}`}
                    alt={
                      plot === "traffic-light"
                        ? `Traffic-light plot of ${variant.studies.length} studies assessed with ${tool.name}.`
                        : `Summary plot: the share of studies at each judgement, domain by domain.`
                    }
                    className="h-auto max-w-full"
                  />
                </div>
                <figcaption className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <span className="mr-auto">
                    {plot === "traffic-light" ? "Traffic-light plot" : "Summary plot"}
                  </span>
                  {(["svg", "png"] as const).map((format) => (
                    <Button key={format} asChild variant="outline" size="sm">
                      <a
                        href={robPlotUrl(pid, tool.key, {
                          plot,
                          variant: variant.variant_key,
                          format,
                        })}
                        download
                      >
                        <DownloadIcon aria-hidden="true" />
                        {format.toUpperCase()}
                      </a>
                    </Button>
                  ))}
                </figcaption>
              </figure>
            ))}
            <JudgementTable
              tool={tool}
              variantKey={variant.variant_key}
              studies={variant.studies}
            />
          </section>
        ))
      )}
    </div>
  );
}

/** The traffic-light plot's judgements as a table, for reading aloud and copying. */
function JudgementTable({
  tool,
  variantKey,
  studies,
}: {
  tool: RobTool;
  variantKey: string;
  studies: RobSummary["variants"][number]["studies"];
}) {
  const variant = tool.variants.find((v) => v.key === variantKey);
  if (!variant) return null;
  const columns = variant.domains.flatMap((domain) =>
    domain.axes.map((axis) => ({
      key: `${domain.key}.${axis.key}`,
      name: domain.axes.length > 1 ? `${domain.name}: ${axis.name}` : domain.name,
      labels: new Map(axis.judgements.map((choice) => [choice.key, choice.label])),
    })),
  );
  const overall = new Map(
    (variant.domains[0]?.axes[0]?.judgements ?? []).map((choice) => [choice.key, choice.label]),
  );
  return (
    <details className="rounded-xl border border-border bg-card text-sm">
      <summary className="cursor-pointer px-4 py-3 font-medium">The judgements as a table</summary>
      <div className="overflow-x-auto px-4 pb-4">
        <table className="w-full min-w-[40rem]">
          <caption className="sr-only">Judgements by study and domain</caption>
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">
                Study
              </th>
              {columns.map((column) => (
                <th key={column.key} scope="col" className="px-2 py-2 font-medium">
                  {column.name}
                </th>
              ))}
              <th scope="col" className="py-2 pl-2 font-medium">
                Overall
              </th>
            </tr>
          </thead>
          <tbody>
            {studies.map((row) => (
              <tr key={row.record_id} className="border-t border-border">
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {row.label}
                </th>
                {columns.map((column) => {
                  const judgement = row.cells[column.key];
                  return (
                    <td key={column.key} className="px-2 py-2">
                      {judgement ? (
                        <JudgementMark
                          judgement={judgement}
                          label={column.labels.get(judgement) ?? judgement}
                        />
                      ) : (
                        "—"
                      )}
                    </td>
                  );
                })}
                <td className="py-2 pl-2">
                  {row.overall ? (
                    <JudgementMark
                      judgement={row.overall}
                      label={overall.get(row.overall) ?? row.overall}
                    />
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

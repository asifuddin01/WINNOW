import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CopyCheckIcon, SearchIcon, WandSparklesIcon } from "lucide-react";
import { useCallback, useState } from "react";

import {
  autoResolve,
  clustersQuery,
  dedupKeys,
  dedupSummaryQuery,
  ignoreCluster,
  mergeCluster,
  runDedup,
} from "@/api/dedup";
import { projectKeys, projectQuery } from "@/api/projects";
import { recordKeys } from "@/api/records";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ClusterCard } from "@/features/dedup/ClusterCard";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";

export const Route = createFileRoute("/_app/p/$pid/duplicates")({
  component: DuplicatesPage,
  staticData: { title: "Duplicates" },
});

function DuplicatesPage() {
  const { pid } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: project } = useQuery(projectQuery(pid));
  const { data: summary } = useQuery(dedupSummaryQuery(pid));
  const { data: clusters, isPending } = useQuery(clustersQuery(pid));
  const [running, setRunning] = useState(false);

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: dedupKeys.all(pid) });
    void queryClient.invalidateQueries({ queryKey: recordKeys.facets(pid) });
    void queryClient.invalidateQueries({ queryKey: projectKeys.detail(pid) });
  }, [pid, queryClient]);

  // The worker says when it has finished looking.
  const onEvent = useCallback(
    (event: ProjectEvent) => {
      if (!event.event.startsWith("dedup.")) return;
      if (event.event === "dedup.finished") setRunning(false);
      refresh();
    },
    [refresh],
  );
  useProjectEvents(pid, onEvent);

  const invalidate = [dedupKeys.all(pid), recordKeys.facets(pid), projectKeys.detail(pid)];
  const find = useProjectMutation(() => runDedup(pid), {
    invalidate,
    success: "Looking for duplicates…",
  });
  const merge = useProjectMutation(
    ({ cid, primaryId }: { cid: string; primaryId: string }) => mergeCluster(pid, cid, primaryId),
    { invalidate, success: "Merged." },
  );
  const ignore = useProjectMutation((cid: string) => ignoreCluster(pid, cid), {
    invalidate,
    success: "Kept apart.",
  });
  const resolveAll = useProjectMutation(() => autoResolve(pid), {
    invalidate,
    success: "Merged every group Winnow was sure about.",
  });

  if (!project) return null;
  const canDecide = project.permissions.includes("import");
  const certain = summary?.certain ?? 0;

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Duplicates</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            The same work often arrives from more than one database. Winnow groups the copies and
            keeps the fullest one; nothing is deleted, and PRISMA counts what was merged.
          </p>
        </div>
        {canDecide && (
          <Button
            variant="outline"
            disabled={find.isPending || running}
            onClick={() => {
              setRunning(true);
              find.mutate(undefined);
            }}
          >
            <SearchIcon aria-hidden="true" />
            {running || find.isPending ? "Looking…" : "Find duplicates"}
          </Button>
        )}
      </div>

      {summary && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Figure label="Waiting for you" value={summary.pending} />
          <Figure label="Winnow is sure" value={summary.certain} />
          <Figure label="Merged" value={summary.duplicates} />
          <Figure label="Kept apart" value={summary.ignored} />
        </dl>
      )}

      {canDecide && certain > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/40 p-3">
          <WandSparklesIcon className="size-4 text-muted-foreground" aria-hidden="true" />
          <p className="flex-1 text-sm">
            {certain} group{certain === 1 ? "" : "s"} share a DOI or PubMed id, or are all but
            identical.
          </p>
          <Button
            size="sm"
            disabled={resolveAll.isPending}
            onClick={() => {
              resolveAll.mutate(undefined);
            }}
          >
            Merge them all
          </Button>
        </div>
      )}

      {isPending ? (
        <div className="grid gap-3" aria-busy="true">
          <Skeleton className="h-48 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      ) : clusters && clusters.length > 0 ? (
        <ul className="grid gap-4">
          {clusters.map((cluster) => (
            <li key={cluster.id}>
              <ClusterCard
                cluster={cluster}
                canDecide={canDecide}
                busy={merge.isPending || ignore.isPending}
                onMerge={(primaryId) => {
                  merge.mutate({ cid: cluster.id, primaryId });
                }}
                onIgnore={() => {
                  ignore.mutate(cluster.id);
                }}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="grid justify-items-center gap-2 rounded-xl border border-dashed border-input p-10 text-center text-sm text-muted-foreground">
          <CopyCheckIcon className="size-6" aria-hidden="true" />
          {summary && summary.duplicates > 0
            ? `Nothing left to decide. ${summary.duplicates.toLocaleString()} duplicate${
                summary.duplicates === 1 ? " has" : "s have"
              } been merged.`
            : "No duplicates found. Run it again after the next import."}
        </p>
      )}
    </div>
  );
}

function Figure({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums">{value.toLocaleString()}</dd>
    </div>
  );
}

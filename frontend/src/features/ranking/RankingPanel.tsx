import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { RefreshCwIcon } from "lucide-react";
import { useCallback } from "react";
import { toast } from "sonner";

import { rankingKeys, rankingStatusQuery, recallCurveQuery, trainRanking } from "@/api/ranking";
import type { RankingStatus } from "@/api/ranking";
import type { Stage } from "@/api/screening";
import { Button } from "@/components/ui/button";
import { Section } from "@/features/account/Section";
import type { Series } from "@/features/ranking/curve";
import { RecallChart } from "@/features/ranking/RecallChart";
import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";
import { timeAgo } from "@/lib/format";

/**
 * Guide 8.10 on the review's overview: whether the relevance model exists, what it has
 * learnt from (for those allowed to know), retraining on demand, and the recall curve.
 */
export function RankingPanel({
  pid,
  stage = "title_abstract",
  canTrain,
  canConfigure,
}: {
  pid: string;
  stage?: Stage;
  canTrain: boolean;
  canConfigure: boolean;
}) {
  const queryClient = useQueryClient();
  const { data: status } = useQuery(rankingStatusQuery(pid, stage));
  const { data: curve } = useQuery(recallCurveQuery(pid, stage));
  const train = useMutation({
    mutationFn: () => trainRanking(pid, stage),
    onSuccess: (started) => {
      toast.success(
        started.queued ? "Retraining. The order updates in a minute." : "Ranking is off.",
      );
      void queryClient.invalidateQueries({ queryKey: rankingKeys.all(pid) });
    },
  });
  const onEvent = useCallback(
    (event: ProjectEvent) => {
      if (event.event === "ranking.updated") {
        void queryClient.invalidateQueries({ queryKey: rankingKeys.all(pid) });
      }
    },
    [pid, queryClient],
  );
  useProjectEvents(pid, onEvent);

  if (!status) return null;
  const series: Series[] = [];
  if (curve?.team) series.push({ key: "team", label: "Team", curve: curve.team });
  if (curve && curve.mine.screened > 0)
    series.push({ key: "mine", label: "You", curve: curve.mine });

  return (
    <Section
      title="Relevance ranking"
      description="Winnow learns from the review's decisions on this server and puts the records most likely to be relevant first. Nothing leaves the server."
      aside={
        status.enabled && canTrain ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={train.isPending || status.training}
            onClick={() => {
              train.mutate();
            }}
          >
            <RefreshCwIcon aria-hidden="true" className={status.training ? "animate-spin" : ""} />
            {status.training ? "Training…" : "Retrain now"}
          </Button>
        ) : undefined
      }
    >
      <div className="grid gap-4">
        <p className="max-w-[75ch] text-sm">
          <StatusLine status={status} />
        </p>
        {!status.enabled && canConfigure && (
          <Link
            to="/p/$pid/settings/screening"
            params={{ pid }}
            className="text-sm font-medium text-primary underline-offset-4 hover:underline"
          >
            Turn ranking on in the screening settings
          </Link>
        )}
        {series.length > 0 && curve ? (
          <RecallChart series={series} caption={captionFor(series, curve.total)} />
        ) : (
          <p className="text-sm text-muted-foreground">
            The recall curve starts with the first decision.
          </p>
        )}
      </div>
    </Section>
  );
}

function StatusLine({ status }: { status: RankingStatus }) {
  if (!status.enabled) return <>Ranking is off for this review: the queue is in random order.</>;
  const model = status.model;
  if (model) {
    const learnt =
      model.n_labeled != null
        ? ` on ${model.n_labeled.toLocaleString()} decided records (${model.n_included?.toLocaleString() ?? 0} relevant)`
        : " on the team's decisions";
    const auc =
      model.auc != null
        ? ` Cross-validated AUC ${model.auc.toFixed(2)}: the chance it ranks a relevant record above an irrelevant one.`
        : "";
    return (
      <>
        Trained {timeAgo(model.trained_at)}
        {learnt}; {model.scored.toLocaleString()} records ranked. It retrains after every{" "}
        {status.retrain_after} decisions.{auc} In relevance order, one record in{" "}
        {status.explore_every} is picked at random instead, so the model also learns from records it
        would rank low.
      </>
    );
  }
  const counts =
    status.have_included != null && status.have_excluded != null
      ? ` So far: ${Math.min(status.have_included, status.needs_each)} of ${status.needs_each} relevant, ${Math.min(status.have_excluded, status.needs_each)} of ${status.needs_each} excluded.`
      : "";
  return (
    <>
      The first model is trained once the team has decided {status.needs_each} relevant and{" "}
      {status.needs_each} excluded records; until then the queue is in random order.{counts}
    </>
  );
}

function captionFor(series: Series[], total: number): string {
  const parts = series.map(
    (line) =>
      `${line.label}: ${line.curve.found_at.length.toLocaleString()} relevant in ${line.curve.screened.toLocaleString()} screened`,
  );
  return `Recall curve. ${parts.join("; ")}. ${total.toLocaleString()} records in the review.`;
}

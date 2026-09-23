import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ScaleIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { membersQuery, projectQuery, reasonsQuery } from "@/api/projects";
import {
  conflictsQuery,
  discussConflict,
  resolveConflict,
  screeningKeys,
  type FinalDecision,
} from "@/api/screening";
import { SelectField } from "@/components/forms/SelectField";
import { Skeleton } from "@/components/ui/skeleton";
import { ConflictCard } from "@/features/conflicts/ConflictCard";

export const Route = createFileRoute("/_app/p/$pid/conflicts")({
  validateSearch: (search: Record<string, unknown>): { record?: string } =>
    typeof search.record === "string" ? { record: search.record } : {},
  component: ConflictsPage,
  staticData: { title: "Conflicts" },
});

const ANYONE = "";

function ConflictsPage() {
  const { pid } = Route.useParams();
  const { record } = Route.useSearch();
  const queryClient = useQueryClient();
  const { data: project } = useQuery(projectQuery(pid));
  const canResolve = project?.permissions.includes("resolve_conflicts") ?? false;
  const { data: members } = useQuery({ ...membersQuery(pid), enabled: canResolve });
  const { data: allReasons = [] } = useQuery(reasonsQuery(pid));
  const [pair, setPair] = useState({ a: ANYONE, b: ANYONE });
  const { data: page, isPending } = useQuery({
    ...conflictsQuery(pid, "title_abstract", pair),
    enabled: canResolve,
  });
  const [busy, setBusy] = useState<string | null>(null);

  // Opened from a "please discuss" email: bring that record into view.
  useEffect(() => {
    if (record && page) {
      document.getElementById(`conflict-${record}`)?.scrollIntoView({ block: "start" });
    }
  }, [record, page]);

  if (!project) return null;
  if (!canResolve) {
    return (
      <div className="mx-auto grid max-w-xl gap-2 px-4 py-10 text-center">
        <h1 className="text-2xl font-semibold">Conflicts</h1>
        <p className="text-muted-foreground">
          Resolving disagreements is for the review's owners and admins, and for reviewers they
          trust with it. While blind mode is on, it is also where others' decisions are shown.
        </p>
      </div>
    );
  }

  const reasons = allReasons.filter((r) => r.stage === "title_abstract" || r.stage === "both");
  const people = [
    { value: ANYONE, label: "Anyone" },
    ...(members?.items ?? []).map((member) => ({ value: member.user.id, label: member.user.name })),
  ];
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["projects", pid, "conflicts"] });
    void queryClient.invalidateQueries({ queryKey: screeningKeys.all(pid) });
  };

  const resolve = async (
    rid: string,
    decision: FinalDecision,
    reasonIds: string[],
    note: string,
  ) => {
    setBusy(rid);
    try {
      await resolveConflict(pid, rid, {
        stage: "title_abstract",
        final_decision: decision,
        reason_ids: decision === "exclude" ? reasonIds : [],
        note: note || undefined,
      });
      toast.success(decision === "include" ? "Included." : "Excluded.");
      refresh();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const discuss = async (rid: string, body: string) => {
    try {
      await discussConflict(pid, rid, body, "title_abstract");
      toast.success("Note left, and the reviewers have been emailed.");
      refresh();
    } catch (error) {
      toast.error(errorMessage(error));
      throw error;
    }
  };

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Conflicts</h1>
        <p className="mt-1 max-w-2xl text-muted-foreground">
          Records the reviewers disagree on at title and abstract. Blind mode is lifted here, for
          these records only, so the decisions can be read side by side.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-xl">
        <SelectField
          label="Between"
          value={pair.a}
          options={people}
          onChange={(a) => {
            setPair((current) => ({ ...current, a }));
          }}
        />
        <SelectField
          label="And"
          value={pair.b}
          options={people}
          onChange={(b) => {
            setPair((current) => ({ ...current, b }));
          }}
        />
      </div>

      {isPending ? (
        <div className="grid gap-3" aria-busy="true">
          <Skeleton className="h-56 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      ) : page && page.items.length > 0 ? (
        <>
          <p className="text-sm text-muted-foreground" role="status">
            {page.total.toLocaleString()} record{page.total === 1 ? "" : "s"} to resolve
          </p>
          <ul className="grid gap-4">
            {page.items.map((conflict) => (
              <li key={conflict.record_id}>
                <ConflictCard
                  conflict={conflict}
                  reasons={reasons}
                  highlighted={conflict.record_id === record}
                  busy={busy === conflict.record_id}
                  onResolve={(decision, reasonIds, note) =>
                    void resolve(conflict.record_id, decision, reasonIds, note)
                  }
                  onDiscuss={(body) => discuss(conflict.record_id, body)}
                />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="grid justify-items-center gap-2 rounded-xl border border-dashed border-input p-10 text-center">
          <ScaleIcon className="size-6 text-muted-foreground" aria-hidden="true" />
          <p className="font-medium">No conflicts.</p>
          <p className="text-sm text-muted-foreground">
            When two reviewers disagree on a record, it appears here.{" "}
            <Link to="/p/$pid/screen/ta" params={{ pid }} className="underline underline-offset-2">
              Back to screening
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}

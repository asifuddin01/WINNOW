import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, ListChecksIcon, XIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { ApiError, errorMessage } from "@/api/client";
import { reasonsQuery } from "@/api/projects";
import type { RecordQuery } from "@/api/records";
import { applyBulk, previewBulk, type BulkDecision, type FinalDecision } from "@/api/screening";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ReasonChips } from "@/features/screening/DecisionPanel";
import { cn } from "@/lib/utils";

/**
 * Guide 8.5's bulk action for owners and admins: decide every record the current search
 * and filters match — "exclude all editorials" — as a final decision. The count is shown
 * first, and the server refuses if it has changed by the time the person confirms.
 */
export function BulkDecisionButton({ pid, query }: { pid: string; query: RecordQuery }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<FinalDecision>("exclude");
  const [reasonIds, setReasonIds] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const noteId = useId();
  const { data: allReasons = [] } = useQuery(reasonsQuery(pid));
  const reasons = allReasons.filter((r) => r.stage === "title_abstract" || r.stage === "both");

  const body: BulkDecision = {
    stage: "title_abstract",
    final_decision: decision,
    q: query.q ?? "",
    status: query.status,
    batch: query.batch,
    reason_ids: decision === "exclude" ? reasonIds : [],
    note: note || null,
    expected: 0,
  };
  const {
    data: count,
    isPending,
    refetch,
  } = useQuery({
    queryKey: ["projects", pid, "bulk-preview", body.q, body.status, body.batch],
    queryFn: () => previewBulk(pid, body),
    enabled: open,
  });

  const confirm = async () => {
    if (count === undefined) return;
    setSaving(true);
    setProblem(null);
    try {
      const decided = await applyBulk(pid, { ...body, expected: count });
      toast.success(
        `${decision === "exclude" ? "Excluded" : "Included"} ${decided.toLocaleString()} record${decided === 1 ? "" : "s"}.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["projects", pid] });
      setOpen(false);
    } catch (error) {
      setProblem(errorMessage(error));
      if (error instanceof ApiError && error.status === 409) void refetch();
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        <ListChecksIcon aria-hidden="true" /> Decide these records
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Decide every record shown</SheetTitle>
            <SheetDescription>
              A final title and abstract decision for each record the search and filters match,
              logged as a bulk action. Records already settled are left alone.
            </SheetDescription>
          </SheetHeader>
          <div className="grid gap-4 px-4 pb-6">
            {problem && <FormAlert>{problem}</FormAlert>}
            <div role="radiogroup" aria-label="Decision" className="grid grid-cols-2 gap-2">
              {(["exclude", "include"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={decision === option}
                  onClick={() => {
                    setDecision(option);
                  }}
                  className={cn(
                    "flex min-h-11 items-center justify-center gap-1.5 rounded-md border font-medium",
                    decision === option &&
                      option === "exclude" &&
                      "border-exclude bg-exclude-muted",
                    decision === option &&
                      option === "include" &&
                      "border-include bg-include-muted",
                    decision !== option && "border-border",
                  )}
                >
                  {option === "exclude" ? (
                    <XIcon className="size-4" aria-hidden="true" />
                  ) : (
                    <CheckIcon className="size-4" aria-hidden="true" />
                  )}
                  {option === "exclude" ? "Exclude" : "Include"}
                </button>
              ))}
            </div>
            {decision === "exclude" && (
              <ReasonChips
                reasons={reasons}
                selected={reasonIds}
                numbered={false}
                onToggle={(id) => {
                  setReasonIds((selected) =>
                    selected.includes(id) ? selected.filter((r) => r !== id) : [...selected, id],
                  );
                }}
              />
            )}
            <div className="grid gap-1 text-sm">
              <label htmlFor={noteId} className="font-medium">
                Note (kept with each decision)
              </label>
              <Textarea
                id={noteId}
                rows={2}
                value={note}
                onChange={(event) => {
                  setNote(event.target.value);
                }}
              />
            </div>
            <p className="text-sm" role="status">
              {isPending
                ? "Counting…"
                : `${(count ?? 0).toLocaleString()} record${count === 1 ? "" : "s"} will be ${
                    decision === "exclude" ? "excluded" : "included"
                  }.`}
            </p>
            <Button
              disabled={saving || isPending || !count}
              onClick={() => void confirm()}
              className={cn(
                "text-white dark:text-background",
                decision === "exclude"
                  ? "bg-exclude hover:bg-exclude/90"
                  : "bg-include hover:bg-include/90",
              )}
            >
              {decision === "exclude" ? "Exclude" : "Include"} {(count ?? 0).toLocaleString()}{" "}
              record{count === 1 ? "" : "s"}
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

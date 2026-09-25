import { useQuery } from "@tanstack/react-query";
import { ChevronDownIcon, ChevronUpIcon, TrashIcon } from "lucide-react";
import { useState } from "react";

import {
  addReason,
  deleteReason,
  projectKeys,
  reasonsQuery,
  updateReason,
  type ReasonStage,
} from "@/api/projects";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { REASON_STAGES } from "@/features/projects/wording";

const STAGE_OPTIONS = Object.entries(REASON_STAGES).map(([value, label]) => ({
  value: value as ReasonStage,
  label,
}));

/** Why a record was excluded: the list reviewers pick from, and PRISMA counts later. */
export function ReasonsEditor({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const { data: reasons = [] } = useQuery(reasonsQuery(pid));
  const invalidate = [projectKeys.reasons(pid)];
  const add = useProjectMutation(
    (values: { label: string; stage: ReasonStage }) => addReason(pid, values),
    { invalidate },
  );
  const move = useProjectMutation(
    ({ id, position }: { id: string; position: number }) => updateReason(pid, id, { position }),
    { invalidate },
  );
  const remove = useProjectMutation((id: string) => deleteReason(pid, id), {
    invalidate,
    success: "Reason deleted.",
  });
  const [label, setLabel] = useState("");
  const [stage, setStage] = useState<ReasonStage>("both");

  return (
    <div className="grid gap-4">
      <ul className="grid gap-2">
        {reasons.map((reason, index) => (
          <li
            key={reason.id}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-3"
          >
            <span className="min-w-40 flex-1 text-sm">{reason.label}</span>
            <Badge variant="outline">{REASON_STAGES[reason.stage]}</Badge>
            {canEdit && (
              <span className="ml-auto flex items-center gap-0.5">
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  disabled={index === 0}
                  aria-label={`Move “${reason.label}” up`}
                  onClick={() => {
                    move.mutate({ id: reason.id, position: reason.position - 1 });
                  }}
                >
                  <ChevronUpIcon aria-hidden="true" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  disabled={index === reasons.length - 1}
                  aria-label={`Move “${reason.label}” down`}
                  onClick={() => {
                    move.mutate({ id: reason.id, position: reason.position + 1 });
                  }}
                >
                  <ChevronDownIcon aria-hidden="true" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-8 text-muted-foreground hover:text-destructive"
                  aria-label={`Delete “${reason.label}”`}
                  onClick={() => {
                    remove.mutate(reason.id);
                  }}
                >
                  <TrashIcon aria-hidden="true" />
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="grid gap-3 rounded-lg border border-dashed border-input p-4 sm:grid-cols-[1fr_14rem_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            if (!label.trim()) return;
            add.mutate({ label: label.trim(), stage });
            setLabel("");
          }}
        >
          <TextField
            label="New reason"
            placeholder="Wrong setting"
            value={label}
            onChange={(event) => {
              setLabel(event.target.value);
            }}
          />
          <SelectField
            label="Offered at"
            value={stage}
            options={STAGE_OPTIONS}
            onChange={setStage}
          />
          <Button type="submit" variant="outline" disabled={add.isPending}>
            Add reason
          </Button>
        </form>
      )}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, TrashIcon, XIcon } from "lucide-react";
import { useState } from "react";

import {
  addCriterion,
  criteriaQuery,
  deleteCriterion,
  projectKeys,
  updateCriterion,
  type Criterion,
  type CriterionKind,
} from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

const KINDS: CriterionKind[] = ["inclusion", "exclusion"];
const HEADINGS: Record<CriterionKind, string> = {
  inclusion: "Include a record when",
  exclusion: "Exclude a record when",
};
const NEW_LABELS: Record<CriterionKind, string> = {
  inclusion: "New inclusion criterion",
  exclusion: "New exclusion criterion",
};
const PLACEHOLDERS: Record<CriterionKind, string> = {
  inclusion: "Adults aged 18 or over",
  exclusion: "Animal studies",
};

/** The inclusion and exclusion criteria, in the order reviewers should read them. */
export function CriteriaEditor({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const { data: criteria = [] } = useQuery(criteriaQuery(pid));
  const invalidate = [projectKeys.criteria(pid)];
  const add = useProjectMutation(
    (values: { kind: CriterionKind; text: string }) => addCriterion(pid, values),
    { invalidate },
  );
  const change = useProjectMutation(
    ({ id, ...body }: { id: string; text?: string; position?: number }) =>
      updateCriterion(pid, id, body),
    { invalidate },
  );
  const remove = useProjectMutation((id: string) => deleteCriterion(pid, id), {
    invalidate,
    success: "Criterion deleted.",
  });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {KINDS.map((kind) => {
        const list = criteria.filter((criterion) => criterion.kind === kind);
        return (
          <section
            key={kind}
            aria-labelledby={`criteria-${kind}`}
            className="grid content-start gap-3"
          >
            <h3 id={`criteria-${kind}`} className="text-sm font-semibold">
              {HEADINGS[kind]}
            </h3>
            {list.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing here yet.</p>
            )}
            <ul className="grid gap-2">
              {list.map((criterion, index) => (
                <li key={criterion.id}>
                  <CriterionRow
                    criterion={criterion}
                    canEdit={canEdit}
                    isFirst={index === 0}
                    isLast={index === list.length - 1}
                    onMove={(position) => {
                      change.mutate({ id: criterion.id, position });
                    }}
                    onSave={(text) => {
                      change.mutate({ id: criterion.id, text });
                    }}
                    onDelete={() => {
                      remove.mutate(criterion.id);
                    }}
                  />
                </li>
              ))}
            </ul>
            {canEdit && (
              <AddCriterion
                kind={kind}
                pending={add.isPending}
                onAdd={(text) => {
                  add.mutate({ kind, text });
                }}
              />
            )}
          </section>
        );
      })}
    </div>
  );
}

function CriterionRow({
  criterion,
  canEdit,
  isFirst,
  isLast,
  onMove,
  onSave,
  onDelete,
}: {
  criterion: Criterion;
  canEdit: boolean;
  isFirst: boolean;
  isLast: boolean;
  onMove: (position: number) => void;
  onSave: (text: string) => void;
  onDelete: () => void;
}) {
  const [text, setText] = useState<string | null>(null);

  if (text !== null) {
    return (
      <div className="grid gap-2 rounded-lg border border-border bg-card p-3">
        <Textarea
          aria-label="Criterion"
          value={text}
          rows={2}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => {
              if (text.trim()) onSave(text.trim());
              setText(null);
            }}
          >
            <CheckIcon aria-hidden="true" /> Save
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setText(null);
            }}
          >
            <XIcon aria-hidden="true" /> Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2 rounded-lg border border-border bg-card p-3">
      <p className="flex-1 text-sm">{criterion.text}</p>
      {canEdit && (
        <div className="flex shrink-0 items-center gap-0.5">
          <Button
            size="icon"
            variant="ghost"
            className="size-8"
            disabled={isFirst}
            aria-label={`Move “${criterion.text}” up`}
            onClick={() => {
              onMove(criterion.position - 1);
            }}
          >
            <ChevronUpIcon aria-hidden="true" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-8"
            disabled={isLast}
            aria-label={`Move “${criterion.text}” down`}
            onClick={() => {
              onMove(criterion.position + 1);
            }}
          >
            <ChevronDownIcon aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Edit “${criterion.text}”`}
            onClick={() => {
              setText(criterion.text);
            }}
          >
            Edit
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive"
            aria-label={`Delete “${criterion.text}”`}
            onClick={onDelete}
          >
            <TrashIcon aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}

function AddCriterion({
  kind,
  pending,
  onAdd,
}: {
  kind: CriterionKind;
  pending: boolean;
  onAdd: (text: string) => void;
}) {
  const [text, setText] = useState("");
  return (
    <form
      className="grid gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!text.trim()) return;
        onAdd(text.trim());
        setText("");
      }}
    >
      <Textarea
        aria-label={NEW_LABELS[kind]}
        placeholder={PLACEHOLDERS[kind]}
        rows={2}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      <Button
        type="submit"
        variant="outline"
        size="sm"
        className="justify-self-start"
        disabled={pending}
      >
        Add {kind} criterion
      </Button>
    </form>
  );
}

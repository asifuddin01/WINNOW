import { CheckIcon, LockIcon, UsersIcon } from "lucide-react";
import { useState } from "react";

import type { Label, Reason } from "@/api/projects";
import type { DecisionValue, Note, NoteVisibility, ScreeningItem } from "@/api/screening";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { COLOR_CHIP } from "@/features/projects/palette";
import { DECIDED_TEXT, DECISIONS } from "@/features/screening/wording";
import { cn } from "@/lib/utils";

export function DecisionButtons({
  current,
  onDecide,
  disabled,
  compact = false,
}: {
  current?: DecisionValue | null;
  onDecide: (decision: DecisionValue) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div role="group" aria-label="Decision" className="grid grid-cols-3 gap-2">
      {DECISIONS.map((option) => (
        <Button
          key={option.value}
          type="button"
          disabled={disabled}
          aria-pressed={current === option.value}
          aria-keyshortcuts={option.keys.replace(" or ", " ")}
          onClick={() => {
            onDecide(option.value);
          }}
          className={cn(
            "h-12 min-h-11 flex-col gap-0 text-base font-semibold",
            compact && "h-14",
            option.className,
            current === option.value && "ring-3 ring-ring ring-offset-2 ring-offset-background",
          )}
        >
          <span className="flex items-center gap-1.5">
            <option.icon className="size-5" aria-hidden="true" />
            {option.label}
          </span>
          {!compact && <span className="text-[11px] font-normal opacity-90">{option.keys}</span>}
        </Button>
      ))}
    </div>
  );
}

export function ReasonChips({
  reasons,
  selected,
  onToggle,
  numbered,
}: {
  reasons: Reason[];
  selected: string[];
  onToggle: (id: string) => void;
  numbered: boolean;
}) {
  if (reasons.length === 0) {
    return <p className="text-xs text-muted-foreground">This review has no exclusion reasons.</p>;
  }
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Exclusion reasons">
      {reasons.map((reason, index) => {
        const on = selected.includes(reason.id);
        return (
          <li key={reason.id}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => {
                onToggle(reason.id);
              }}
              className={cn(
                "min-h-9 rounded-full border px-3 py-1 text-sm pointer-coarse:min-h-11 transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                on
                  ? "border-exclude bg-exclude-muted font-medium text-foreground"
                  : "border-border hover:bg-muted",
              )}
            >
              {numbered && index < 9 && (
                <span className="mr-1 font-mono text-xs text-muted-foreground">{index + 1}</span>
              )}
              {on && <CheckIcon className="mr-1 inline size-3.5" aria-hidden="true" />}
              {reason.label}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function LabelChips({
  labels,
  selected,
  onToggle,
}: {
  labels: Label[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  if (labels.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">No labels yet. Add them in the settings.</p>
    );
  }
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Labels">
      {labels.map((label) => {
        const on = selected.includes(label.id);
        return (
          <li key={label.id}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => {
                onToggle(label.id);
              }}
              className={cn(
                "min-h-9 rounded-full border px-3 py-1 text-sm pointer-coarse:min-h-11 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                on ? COLOR_CHIP[label.color] : "border-border text-muted-foreground hover:bg-muted",
              )}
            >
              {on && <CheckIcon className="mr-1 inline size-3.5" aria-hidden="true" />}
              {label.name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function Notes({
  notes,
  onAdd,
  inputId,
}: {
  notes: Note[];
  onAdd: (body: string, visibility: NoteVisibility) => Promise<void>;
  inputId: string;
}) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<NoteVisibility>("private");
  const [saving, setSaving] = useState(false);
  return (
    <div className="grid gap-2">
      {notes.length > 0 && (
        <ul className="grid gap-1.5">
          {notes.map((note) => (
            <li key={note.id} className="rounded-md bg-muted/60 px-2.5 py-1.5 text-sm">
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                {note.visibility === "team" ? (
                  <UsersIcon className="size-3" aria-hidden="true" />
                ) : (
                  <LockIcon className="size-3" aria-hidden="true" />
                )}
                {note.mine ? "You" : note.author} ·{" "}
                {note.visibility === "team" ? "team" : "private"}
              </span>
              <span className="whitespace-pre-line">{note.body}</span>
            </li>
          ))}
        </ul>
      )}
      <label htmlFor={inputId} className="sr-only">
        New note
      </label>
      <Textarea
        id={inputId}
        rows={2}
        value={body}
        placeholder="A note on this record…"
        onChange={(event) => {
          setBody(event.target.value);
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Who sees the note" className="flex gap-1 text-xs">
          {(["private", "team"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={visibility === option}
              onClick={() => {
                setVisibility(option);
              }}
              className={cn(
                "min-h-8 rounded-md border px-2 pointer-coarse:min-h-11",
                visibility === option ? "border-ring bg-muted font-medium" : "border-border",
              )}
            >
              {option === "private" ? "Only me" : "Team"}
            </button>
          ))}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!body.trim() || saving}
          onClick={() => {
            setSaving(true);
            void onAdd(body.trim(), visibility)
              .then(() => {
                setBody("");
              })
              .finally(() => {
                setSaving(false);
              });
          }}
        >
          Add note
        </Button>
      </div>
    </div>
  );
}

export function OthersDecisions({ item, reasons }: { item: ScreeningItem; reasons: Reason[] }) {
  if (!item.others) return null;
  const names = new Map(reasons.map((reason) => [reason.id, reason.label]));
  return (
    <section aria-labelledby={`others-${item.id}`} className="grid gap-1.5">
      <h3
        id={`others-${item.id}`}
        className="text-xs font-semibold text-muted-foreground uppercase"
      >
        Other reviewers
      </h3>
      {item.others.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nobody else has decided yet.</p>
      ) : (
        <ul className="grid gap-1.5">
          {item.others.map((other) => (
            <li key={other.user_id} className="text-sm">
              <span className="font-medium">{other.name}</span>: {DECIDED_TEXT[other.decision]}
              {other.reason_ids.length > 0 && (
                <span className="text-muted-foreground">
                  {" "}
                  ({other.reason_ids.map((id) => names.get(id) ?? "a reason").join(", ")})
                </span>
              )}
              {other.note && <span className="block text-muted-foreground">“{other.note}”</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

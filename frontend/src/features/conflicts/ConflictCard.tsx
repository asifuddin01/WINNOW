import { CheckIcon, MessageSquareIcon, XIcon } from "lucide-react";
import { useId, useState } from "react";

import type { Reason } from "@/api/projects";
import type { Conflict, FinalDecision } from "@/api/screening";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ReasonChips } from "@/features/screening/DecisionPanel";
import { DECIDED_TEXT } from "@/features/screening/wording";
import { cn } from "@/lib/utils";

/**
 * One record the reviewers disagree on (guide 8.7): each decision with its reasons and
 * note, side by side, then the final word — or a note asking them to talk it over.
 */
export function ConflictCard({
  conflict,
  reasons,
  highlighted,
  busy,
  onResolve,
  onDiscuss,
}: {
  conflict: Conflict;
  reasons: Reason[];
  highlighted: boolean;
  busy: boolean;
  onResolve: (decision: FinalDecision, reasonIds: string[], note: string) => void;
  onDiscuss: (body: string) => Promise<void>;
}) {
  const [reasonIds, setReasonIds] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [discussion, setDiscussion] = useState("");
  const [discussing, setDiscussing] = useState(false);
  const [showAbstract, setShowAbstract] = useState(false);
  const noteId = useId();
  const discussId = useId();
  const names = new Map(reasons.map((reason) => [reason.id, reason.label]));

  return (
    <article
      id={`conflict-${conflict.record_id}`}
      aria-labelledby={`conflict-title-${conflict.record_id}`}
      className={cn(
        "grid gap-4 rounded-xl border bg-card p-4",
        highlighted ? "border-ring ring-3 ring-ring/30" : "border-border",
      )}
    >
      <header className="grid gap-1">
        <h2 id={`conflict-title-${conflict.record_id}`} className="font-semibold">
          {conflict.title ?? "(no title)"}
        </h2>
        <p className="text-sm text-muted-foreground">
          {[conflict.authors.slice(0, 3).join("; "), conflict.year, conflict.journal]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {conflict.abstract && (
          <button
            type="button"
            className="justify-self-start text-sm text-muted-foreground underline-offset-2 hover:underline"
            aria-expanded={showAbstract}
            onClick={() => {
              setShowAbstract((open) => !open);
            }}
          >
            {showAbstract ? "Hide the abstract" : "Read the abstract"}
          </button>
        )}
        {showAbstract && (
          <p className="max-w-[75ch] text-[17px] leading-relaxed whitespace-pre-line">
            {conflict.abstract}
          </p>
        )}
      </header>

      <ul className="grid gap-2 sm:grid-cols-2" aria-label="Decisions">
        {conflict.decisions.map((decision) => (
          <li
            key={decision.user_id}
            className={cn(
              "rounded-lg border p-3 text-sm",
              decision.decision === "include" && "border-include/50 bg-include-muted",
              decision.decision === "exclude" && "border-exclude/50 bg-exclude-muted",
              decision.decision === "maybe" && "border-maybe/50 bg-maybe-muted",
            )}
          >
            <p className="font-medium">
              {decision.name}: {DECIDED_TEXT[decision.decision]}
            </p>
            {decision.reason_ids.length > 0 && (
              <p className="text-muted-foreground">
                {decision.reason_ids.map((id) => names.get(id) ?? "a reason").join(", ")}
              </p>
            )}
            {decision.note && <p className="mt-1">“{decision.note}”</p>}
          </li>
        ))}
      </ul>

      {conflict.notes.length > 0 && (
        <ul className="grid gap-1 text-sm" aria-label="Notes">
          {conflict.notes.map((item) => (
            <li key={item.id} className="rounded-md bg-muted/60 px-2.5 py-1.5">
              <span className="text-xs text-muted-foreground">
                {item.mine ? "You" : item.author}
              </span>
              <span className="block whitespace-pre-line">{item.body}</span>
            </li>
          ))}
        </ul>
      )}

      <section aria-label="Resolve" className="grid gap-3 border-t border-border pt-3">
        <ReasonChips
          reasons={reasons}
          selected={reasonIds}
          numbered={false}
          onToggle={(id) => {
            setReasonIds((selected) =>
              selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id],
            );
          }}
        />
        <div className="grid gap-1 text-sm">
          <label htmlFor={noteId} className="font-medium">
            Why (kept with the resolution)
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
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            disabled={busy}
            className="bg-include text-white hover:bg-include/90 dark:text-background"
            onClick={() => {
              onResolve("include", [], note);
            }}
          >
            <CheckIcon aria-hidden="true" /> Include
          </Button>
          <Button
            type="button"
            disabled={busy}
            className="bg-exclude text-white hover:bg-exclude/90 dark:text-background"
            onClick={() => {
              onResolve("exclude", reasonIds, note);
            }}
          >
            <XIcon aria-hidden="true" /> Exclude
          </Button>
        </div>
      </section>

      <form
        className="grid gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!discussion.trim()) return;
          setDiscussing(true);
          void onDiscuss(discussion.trim())
            .then(() => {
              setDiscussion("");
            })
            .finally(() => {
              setDiscussing(false);
            });
        }}
      >
        <div className="grid gap-1 text-sm">
          <label htmlFor={discussId} className="font-medium">
            Discuss
          </label>
          <span id={`${discussId}-hint`} className="text-xs text-muted-foreground">
            Leaves a note the team can see and emails the reviewers of this record.
          </span>
          <Textarea
            id={discussId}
            aria-describedby={`${discussId}-hint`}
            rows={2}
            value={discussion}
            onChange={(event) => {
              setDiscussion(event.target.value);
            }}
          />
        </div>
        <Button
          type="submit"
          variant="outline"
          size="sm"
          className="justify-self-start"
          disabled={discussing || !discussion.trim()}
        >
          <MessageSquareIcon aria-hidden="true" /> Ask them to discuss
        </Button>
      </form>
    </article>
  );
}

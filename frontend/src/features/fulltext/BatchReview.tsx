import { useMutation, useQuery } from "@tanstack/react-query";
import { LoaderCircleIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  batchQuery,
  confirmBatch,
  discardBatch,
  type BatchEntry,
  type FulltextRecord,
} from "@/api/fulltext";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

const SKIP_REASON: Record<NonNullable<BatchEntry["skip"]>, string> = {
  not_pdf: "Not a PDF",
  too_large: "Too large",
  encrypted: "Password-protected in the ZIP",
  system: "Mac system file",
};

const HOW: Record<string, string> = {
  doi: "DOI",
  pmcid: "PMCID",
  pmid: "PMID",
  arxiv: "arXiv id",
  author_year: "author and year",
  title: "title",
};

const NONE = "";

/**
 * Guide 8.8's matching review: every PDF in the ZIP with the record its name points to,
 * for a person to confirm or change before anything is attached.
 */
export function BatchReview({
  pid,
  bid,
  records,
  onDone,
}: {
  pid: string;
  bid: string;
  records: FulltextRecord[];
  onDone: () => void;
}) {
  const { data: batch, error } = useQuery(batchQuery(pid, bid));
  // Entry index → chosen record; entries not in here keep their suggested match.
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const [replace, setReplace] = useState(false);
  const replaceId = useId();

  const choiceOf = (entry: BatchEntry) => chosen[entry.index] ?? entry.match?.record_id ?? NONE;

  const confirm = useMutation({
    mutationFn: () => {
      const choices: Record<string, string> = {};
      for (const entry of batch?.entries ?? []) {
        const choice = choiceOf(entry);
        if (!entry.skip && choice) choices[String(entry.index)] = choice;
      }
      return confirmBatch(pid, bid, choices, replace);
    },
    onSuccess: (applied) => {
      toast.success(
        `${applied.attached} PDF${applied.attached === 1 ? "" : "s"} attached` +
          (applied.skipped ? `, ${applied.skipped} left out.` : ".") +
          " Each opens once the virus scan is done.",
      );
      onDone();
    },
    onError: (failure) => toast.error(errorMessage(failure)),
  });
  const discard = useMutation({
    mutationFn: () => discardBatch(pid, bid),
    onSuccess: onDone,
    onError: (failure) => toast.error(errorMessage(failure)),
  });

  if (error) {
    return (
      <p role="alert" className="text-sm">
        {errorMessage(error)}
      </p>
    );
  }
  if (!batch || batch.status === "checking") {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
        Unpacking {batch?.filename ?? "the ZIP"} and matching each PDF to a record…
      </p>
    );
  }
  if (batch.status === "rejected" || batch.status === "failed") {
    return (
      <div
        role="alert"
        className="grid gap-2 rounded-lg border border-exclude/40 bg-exclude-muted p-3 text-sm"
      >
        <p>{batch.problem ?? "This ZIP could not be used."}</p>
        <Button variant="outline" size="sm" className="justify-self-start" onClick={onDone}>
          Upload another
        </Button>
      </div>
    );
  }
  if (batch.status === "applied") {
    return (
      <Button variant="outline" size="sm" onClick={onDone}>
        Upload another ZIP
      </Button>
    );
  }

  const usable = batch.entries.filter((entry) => !entry.skip);
  const skipped = batch.entries.filter((entry) => entry.skip);
  const attaching = usable.filter((entry) => choiceOf(entry) !== NONE).length;
  const known = new Map(records.map((record) => [record.id, record]));

  return (
    <div className="grid gap-4">
      <p className="text-sm">
        <span className="font-medium">{batch.filename}</span>: {usable.length} PDF
        {usable.length === 1 ? "" : "s"}, {usable.filter((e) => e.match).length} matched from their
        names. Check each one; change a match, or choose &ldquo;Leave out&rdquo;.
      </p>
      <ul className="grid gap-2">
        {usable.map((entry) => (
          <EntryRow
            key={entry.index}
            entry={entry}
            records={records}
            known={known}
            value={choiceOf(entry)}
            onChange={(value) => {
              setChosen((was) => ({ ...was, [entry.index]: value }));
            }}
          />
        ))}
      </ul>
      {skipped.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            {skipped.length} file{skipped.length === 1 ? "" : "s"} left out
          </summary>
          <ul className="mt-2 grid gap-1">
            {skipped.map((entry) => (
              <li key={entry.index} className="flex justify-between gap-2">
                <span className="truncate font-mono text-xs">{entry.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {entry.skip ? SKIP_REASON[entry.skip] : ""}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex items-center gap-2">
        <Checkbox
          id={replaceId}
          checked={replace}
          onCheckedChange={(value) => {
            setReplace(value === true);
          }}
        />
        <Label htmlFor={replaceId} className="font-normal">
          Replace PDFs that records already have
        </Label>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="ghost"
          disabled={discard.isPending || confirm.isPending}
          onClick={() => {
            discard.mutate();
          }}
        >
          Discard the ZIP
        </Button>
        <Button
          disabled={attaching === 0 || confirm.isPending}
          onClick={() => {
            confirm.mutate();
          }}
        >
          Attach {attaching} PDF{attaching === 1 ? "" : "s"}
        </Button>
      </div>
    </div>
  );
}

function EntryRow({
  entry,
  records,
  known,
  value,
  onChange,
}: {
  entry: BatchEntry;
  records: FulltextRecord[];
  known: Map<string, FulltextRecord>;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  // A match or candidate outside full text is still offered, under its own title.
  const extra = [entry.match, ...entry.candidates].filter(
    (item): item is NonNullable<typeof item> => item != null && !known.has(item.record_id),
  );
  const chosenRecord = value ? known.get(value) : undefined;
  const hasPdf =
    (chosenRecord?.fulltext != null && chosenRecord.fulltext.scan_status !== "infected") ||
    extra.some((item) => item.record_id === value && item.has_fulltext);

  return (
    <li className="grid gap-1.5 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="min-w-0 truncate font-mono text-xs">{entry.name}</span>
        <span className="text-xs text-muted-foreground">
          {entry.match
            ? `${entry.match.confidence === "sure" ? "Sure" : "Likely"} match by ${HOW[entry.match.by ?? ""] ?? "name"}`
            : entry.candidates.length > 0
              ? "Several records could be this one"
              : "No match from its name"}
        </span>
      </div>
      <label htmlFor={id} className="sr-only">
        Record for {entry.name}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="h-9 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm"
      >
        <option value={NONE}>Leave out</option>
        {extra.map((item) => (
          <option key={item.record_id} value={item.record_id}>
            {item.title ?? "Untitled"} {item.year ? `(${item.year})` : ""} — not at full text
          </option>
        ))}
        {records.map((record) => (
          <option key={record.id} value={record.id}>
            {record.title ?? "Untitled"}
            {record.first_author ? ` — ${record.first_author}` : ""}
            {record.year ? ` (${record.year})` : ""}
          </option>
        ))}
      </select>
      {hasPdf && (
        <p className="text-xs text-muted-foreground">
          This record already has a PDF; it is kept unless you choose to replace PDFs below.
        </p>
      )}
    </li>
  );
}

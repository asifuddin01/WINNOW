import { CheckIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import {
  confirmImport,
  importKeys,
  undoImport,
  type ImportBatch,
  type ImportUpload,
} from "@/api/imports";
import { projectKeys } from "@/api/projects";
import { recordKeys } from "@/api/records";
import { FormAlert } from "@/components/forms/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PreviewCard } from "@/features/imports/PreviewCard";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

/**
 * What one upload brought: every file Winnow read, with its first records and, for CSV,
 * the column mapping. Nothing is in the review until these are confirmed, and they are
 * confirmed together — a search that arrived in eleven files is one decision, not eleven.
 */
export function PreviewList({
  pid,
  upload,
  onDone,
}: {
  pid: string;
  upload: ImportUpload;
  onDone: () => void;
}) {
  const [mappings, setMappings] = useState<Record<string, Record<string, string>>>({});
  const [started, setStarted] = useState<string[]>([]);
  const invalidate = [importKeys.list(pid), projectKeys.detail(pid), recordKeys.facets(pid)];

  const start = useProjectMutation(
    async (batches: ImportBatch[]) => {
      const done: string[] = [];
      for (const batch of batches) {
        const mapping = mappings[batch.id];
        await confirmImport(pid, batch.id, mapping ? { column_mapping: mapping } : {});
        done.push(batch.id);
        setStarted([...done]);
      }
      return done;
    },
    { invalidate },
  );
  const discard = useProjectMutation(
    async (batches: ImportBatch[]) => {
      for (const batch of batches) await undoImport(pid, batch.id);
    },
    { invalidate, success: "Upload discarded." },
  );

  const pending = upload.batches.filter((batch) => !started.includes(batch.id));
  const records = upload.batches.length;
  const rejected = upload.rejected ?? [];

  return (
    <div className="grid gap-5">
      {start.isError && <FormAlert>{errorMessage(start.error)}</FormAlert>}
      {rejected.length > 0 && (
        <div className="grid gap-1 rounded-lg border border-maybe/40 bg-maybe/5 p-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-maybe">
            <TriangleAlertIcon className="size-4" aria-hidden="true" />
            {rejected.length} file{rejected.length === 1 ? "" : "s"} could not be read
          </p>
          <ul className="text-xs text-muted-foreground">
            {rejected.map((file) => (
              <li key={file.filename}>
                <span className="font-medium">{file.filename}</span> — {file.reason}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">The others are ready below.</p>
        </div>
      )}

      <ul className="grid gap-4">
        {upload.batches.map((batch) => (
          <li key={batch.id} className="rounded-xl border border-border bg-card p-4">
            <PreviewCard
              pid={pid}
              batch={batch}
              mapping={mappings[batch.id]}
              onMappingChange={(mapping) => {
                setMappings((current) => ({ ...current, [batch.id]: mapping }));
              }}
              collapsed={records > 1}
            />
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={start.isPending || pending.length === 0}
          onClick={() => {
            start.mutate(pending, { onSuccess: onDone });
          }}
        >
          <CheckIcon aria-hidden="true" />
          {start.isPending
            ? `Starting ${started.length + 1} of ${pending.length}…`
            : `Import ${records === 1 ? "these records" : `all ${records} files`}`}
        </Button>
        <Button
          variant="ghost"
          disabled={discard.isPending || start.isPending}
          onClick={() => {
            discard.mutate(upload.batches, { onSuccess: onDone });
          }}
        >
          <XIcon aria-hidden="true" /> Discard {records === 1 ? "this file" : "these files"}
        </Button>
        {records > 1 && (
          <Badge variant="secondary">
            {records} imports, one per file, each undoable on its own
          </Badge>
        )}
      </div>
    </div>
  );
}

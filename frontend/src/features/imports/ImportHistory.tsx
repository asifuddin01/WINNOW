import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, FileTextIcon, TrashIcon } from "lucide-react";

import { importKeys, importsQuery, undoImport, type ImportBatch } from "@/api/imports";
import { projectKeys } from "@/api/projects";
import { recordKeys } from "@/api/records";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/features/projects/ConfirmDialog";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { timeAgo } from "@/lib/format";

const STATUS: Record<ImportBatch["status"], string> = {
  queued: "Waiting to be confirmed",
  parsing: "Importing…",
  done: "Imported",
  failed: "Failed",
};

/** Every import in this review, with progress, problems and undo (guide 8.3). */
export function ImportHistory({ pid, canImport }: { pid: string; canImport: boolean }) {
  const { data: batches = [] } = useQuery(importsQuery(pid));
  const undo = useProjectMutation((bid: string) => undoImport(pid, bid), {
    invalidate: [importKeys.list(pid), recordKeys.facets(pid), projectKeys.detail(pid)],
    success: "Import undone.",
  });

  if (batches.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing imported yet. Upload a search export above and Winnow will show you the first
        records before anything is added.
      </p>
    );
  }

  return (
    <ul className="grid gap-3">
      {batches.map((batch) => (
        <li key={batch.id} className="grid gap-2 rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <FileTextIcon className="size-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-medium">{batch.filename}</span>
            <Badge variant={batch.status === "failed" ? "destructive" : "secondary"}>
              {STATUS[batch.status]}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {batch.database_name} · added {timeAgo(batch.created_at)}
            </span>
            {canImport && (
              <ConfirmDialog
                trigger={
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto text-muted-foreground"
                    aria-label={`Undo the import of ${batch.filename}`}
                  >
                    <TrashIcon aria-hidden="true" /> Undo
                  </Button>
                }
                title={`Undo ${batch.filename}?`}
                description={
                  batch.imported > 0
                    ? `The ${batch.imported.toLocaleString()} records this file brought in are removed from the review.`
                    : "This upload is removed."
                }
                confirmLabel="Undo import"
                destructive
                onConfirm={() => {
                  undo.mutate(batch.id);
                }}
              />
            )}
          </div>

          {batch.status === "parsing" && (
            <p className="text-sm" role="status">
              {batch.imported.toLocaleString()} records so far…
            </p>
          )}
          {batch.status === "done" && (
            <p className="text-sm">
              {batch.imported.toLocaleString()} records
              {batch.problems.length > 0 && (
                <span className="text-muted-foreground">
                  {" "}
                  · {batch.problems.length} could not be read
                </span>
              )}
            </p>
          )}
          {batch.problems.length > 0 && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                <DownloadIcon className="mr-1 inline size-3" aria-hidden="true" />
                What could not be read
              </summary>
              <ul className="mt-2 grid gap-1">
                {batch.problems.slice(0, 20).map((problem, index) => (
                  <li key={index}>
                    {problem.unit} {problem.at}: {problem.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {batch.search_string && (
            <p className="text-xs text-muted-foreground">Search: {batch.search_string}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

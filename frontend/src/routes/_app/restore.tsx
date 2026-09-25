import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArchiveRestoreIcon, LoaderIcon } from "lucide-react";
import { useEffect, useId, useState, type SyntheticEvent } from "react";

import { errorMessage } from "@/api/client";
import { restoreQuery, startRestore, working } from "@/api/exports";
import { projectKeys } from "@/api/projects";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/_app/restore")({
  component: RestoreReview,
  staticData: { title: "Restore a review" },
});

/** Guide 8.16: a backup from this Winnow or another one becomes a new review of yours. */
function RestoreReview() {
  const id = useId();
  const [file, setFile] = useState<File | null>(null);
  const [restoreId, setRestoreId] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: startRestore,
    onSuccess: (job) => {
      setRestoreId(job.id);
    },
  });

  const onSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (file) upload.mutate(file);
  };

  return (
    <div className="mx-auto grid w-full max-w-2xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Restore a review</h1>
        <p className="mt-1 text-muted-foreground">
          Upload a backup made in a review's Report → Exports → Full backup, on this Winnow or
          another one. It becomes a new review that you own; the original is not touched.
        </p>
      </div>
      {restoreId ? (
        <Progress
          restoreId={restoreId}
          onAgain={() => {
            setRestoreId(null);
            setFile(null);
            upload.reset();
          }}
        />
      ) : (
        <form
          onSubmit={onSubmit}
          className="grid gap-4 rounded-xl border border-border bg-card p-5"
        >
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-file`}>Backup file (.zip)</Label>
            <Input
              id={`${id}-file`}
              type="file"
              accept=".zip,application/zip"
              aria-describedby={`${id}-hint`}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
              }}
            />
            <p id={`${id}-hint`} className="text-xs text-muted-foreground">
              You will be its only member. People who did the work keep their names on it; those
              with an account here are linked to it. Invite the team again when you are ready.
            </p>
          </div>
          {upload.isError && <FormAlert>{errorMessage(upload.error)}</FormAlert>}
          <div>
            <Button type="submit" disabled={!file || upload.isPending}>
              <ArchiveRestoreIcon aria-hidden="true" />
              {upload.isPending ? "Uploading…" : "Restore"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

function Progress({ restoreId, onAgain }: { restoreId: string; onAgain: () => void }) {
  const queryClient = useQueryClient();
  const { data: job, error } = useQuery(restoreQuery(restoreId));
  const ready = job?.status === "ready";
  useEffect(() => {
    if (ready) void queryClient.invalidateQueries({ queryKey: projectKeys.list });
  }, [ready, queryClient]);
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;
  if (!job || working(job.status)) {
    return (
      <p
        role="status"
        className="flex items-center gap-2 rounded-xl border border-border bg-card p-5 text-sm"
      >
        <LoaderIcon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        Checking the backup and rebuilding the review. Large reviews take a minute or two.
      </p>
    );
  }
  if (job.status === "failed" || !job.project_id) {
    return (
      <div className="grid gap-3">
        <FormAlert>
          {job.problem ?? "The backup could not be restored."} Nothing was kept.
        </FormAlert>
        <div>
          <Button variant="outline" onClick={onAgain}>
            Try another file
          </Button>
        </div>
      </div>
    );
  }
  const records = job.restored.records ?? 0;
  return (
    <div className="grid gap-3">
      <FormAlert tone="success">
        Restored {records.toLocaleString()} {records === 1 ? "record" : "records"} with their
        decisions and files. PDFs are scanned again before they open.
      </FormAlert>
      <div>
        <Button asChild>
          <Link to="/p/$pid" params={{ pid: job.project_id }}>
            Open the restored review
          </Link>
        </Button>
      </div>
    </div>
  );
}

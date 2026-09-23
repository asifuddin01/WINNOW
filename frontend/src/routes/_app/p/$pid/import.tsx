import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useState } from "react";

import { importKeys, type ImportBatch } from "@/api/imports";
import { projectQuery } from "@/api/projects";
import { recordKeys } from "@/api/records";
import { Section } from "@/features/account/Section";
import { ImportHistory } from "@/features/imports/ImportHistory";
import { PreviewCard } from "@/features/imports/PreviewCard";
import { UploadCard } from "@/features/imports/UploadCard";
import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";

export const Route = createFileRoute("/_app/p/$pid/import")({
  component: ImportPage,
  staticData: { title: "Import" },
});

function ImportPage() {
  const { pid } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: project } = useQuery(projectQuery(pid));
  const [uploaded, setUploaded] = useState<ImportBatch | null>(null);

  // Progress arrives on the project's event stream; refresh what it changes.
  const onEvent = useCallback(
    (event: ProjectEvent) => {
      if (!event.event.startsWith("import.")) return;
      void queryClient.invalidateQueries({ queryKey: importKeys.list(pid) });
      if (event.event === "import.finished") {
        void queryClient.invalidateQueries({ queryKey: recordKeys.facets(pid) });
      }
    },
    [pid, queryClient],
  );
  useProjectEvents(pid, onEvent);

  if (!project) return null;
  const canImport = project.permissions.includes("import");

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-8 md:px-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Import</h1>
        <p className="mt-1 text-muted-foreground">
          Bring in search results, one export at a time. Nothing is added until you have seen what
          Winnow read.
        </p>
      </div>

      {canImport &&
        (uploaded ? (
          <Section title="Check before importing" description={uploaded.filename}>
            <PreviewCard
              pid={pid}
              batch={uploaded}
              onStarted={() => {
                setUploaded(null);
              }}
              onCancelled={() => {
                setUploaded(null);
              }}
            />
          </Section>
        ) : (
          <Section
            title="Upload a search export"
            description="Record which database it came from; PRISMA asks for that later."
          >
            <UploadCard pid={pid} onUploaded={setUploaded} />
          </Section>
        ))}

      <Section
        title="Import history"
        description={
          canImport
            ? "Every file, what came in, and what could not be read."
            : "What has been imported into this review."
        }
      >
        <ImportHistory pid={pid} canImport={canImport} />
      </Section>
    </div>
  );
}

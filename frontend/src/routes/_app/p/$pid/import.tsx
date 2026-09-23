import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useState } from "react";

import { importKeys, type ImportUpload } from "@/api/imports";
import { projectQuery } from "@/api/projects";
import { recordKeys } from "@/api/records";
import { Section } from "@/features/account/Section";
import { ImportHistory } from "@/features/imports/ImportHistory";
import { PreviewList } from "@/features/imports/PreviewList";
import { UploadCard } from "@/features/imports/UploadCard";
import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";

// Guide 8.3 and the instance's max_upload_files: a whole search at once, not file by file.
const MAX_FILES = 20;

export const Route = createFileRoute("/_app/p/$pid/import")({
  component: ImportPage,
  staticData: { title: "Import" },
});

function ImportPage() {
  const { pid } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: project } = useQuery(projectQuery(pid));
  const [uploaded, setUploaded] = useState<ImportUpload | null>(null);

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
          Bring in your search results — up to {MAX_FILES} exports at once. Nothing is added until
          you have seen what Winnow read.
        </p>
      </div>

      {canImport &&
        (uploaded ? (
          <Section
            title="Check before importing"
            description={
              uploaded.batches.length === 1
                ? uploaded.batches[0]?.filename
                : `${uploaded.batches.length} files`
            }
          >
            <PreviewList
              pid={pid}
              upload={uploaded}
              onDone={() => {
                setUploaded(null);
              }}
            />
          </Section>
        ) : (
          <Section
            title="Upload your search exports"
            description="As many files as one search produced. Record which database each came from; PRISMA asks for that later."
          >
            <UploadCard pid={pid} limit={MAX_FILES} onUploaded={setUploaded} />
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

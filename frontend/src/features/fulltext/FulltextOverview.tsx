import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  BanIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  FileArchiveIcon,
  FileUpIcon,
  LoaderCircleIcon,
  ShieldAlertIcon,
} from "lucide-react";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  fulltextKeys,
  fulltextRecordsQuery,
  fulltextSummaryQuery,
  readable,
  uploadPdf,
  uploadZip,
  type FulltextRecord,
} from "@/api/fulltext";
import { projectQuery } from "@/api/projects";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { BatchReview } from "@/features/fulltext/BatchReview";
import { FullTextPanel } from "@/features/fulltext/FullTextPanel";
import { useIsMobile } from "@/hooks/use-mobile";
import { useProjectEvents, type ProjectEvent } from "@/hooks/use-project-events";
import { cn } from "@/lib/utils";

type Filter = "all" | "missing" | "scanning" | "quarantined" | "pdf" | "not_retrievable";

const ROW_HEIGHT = 64;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "missing", label: "Missing" },
  { value: "scanning", label: "Being scanned" },
  { value: "quarantined", label: "Quarantined" },
  { value: "pdf", label: "With PDF" },
  { value: "not_retrievable", label: "Not retrievable" },
];

function stateOf(record: FulltextRecord): Exclude<Filter, "all"> {
  if (record.not_retrievable) return "not_retrievable";
  const status = record.fulltext?.scan_status;
  if (!status) return "missing";
  if (readable(status)) return "pdf";
  if (status === "infected") return "quarantined";
  return "scanning";
}

/**
 * The full-text stage at a glance (guide 8.8): which records have their PDF, adding PDFs
 * one by one (drop one onto its record) or as a ZIP, and opening any of them.
 */
export function FulltextOverview({ pid }: { pid: string }) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const { data: project } = useQuery(projectQuery(pid));
  const { data: summary } = useQuery(fulltextSummaryQuery(pid));
  const { data: records = [], isPending } = useQuery(fulltextRecordsQuery(pid));
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<FulltextRecord | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);

  const canScreen = Boolean(project?.permissions.includes("screen"));
  const canImport = Boolean(project?.permissions.includes("import"));

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: fulltextKeys.summary(pid) });
    void queryClient.invalidateQueries({ queryKey: fulltextKeys.records(pid) });
  }, [pid, queryClient]);

  useProjectEvents(
    pid,
    useCallback(
      (event: ProjectEvent) => {
        if (event.event === "fulltext" || event.event === "fulltext_batch") refresh();
      },
      [refresh],
    ),
  );

  const shown = useMemo(
    () => (filter === "all" ? records : records.filter((record) => stateOf(record) === filter)),
    [records, filter],
  );

  return (
    <div className="grid gap-6">
      {summary && (
        <section aria-labelledby="pdf-summary" className="grid gap-2">
          <h2 id="pdf-summary" className="sr-only">
            PDFs at full text
          </h2>
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
            <Tile label="At full text" value={summary.records} />
            <Tile label="With PDF" value={summary.with_pdf} />
            <Tile label="Missing" value={summary.missing} />
            <Tile label="Being scanned" value={summary.scanning} />
            <Tile label="Quarantined" value={summary.quarantined} />
            <Tile label="Not retrievable" value={summary.not_retrievable} />
          </dl>
          {!summary.scanner && (
            <p className="text-sm text-muted-foreground">
              This Winnow runs without a virus scanner (started with <code>make local</code>), so
              PDFs are not scanned before they open.
            </p>
          )}
        </section>
      )}

      {canImport && (
        <section aria-labelledby="zip-heading" className="grid gap-3">
          <h2 id="zip-heading" className="text-base font-semibold">
            Add many PDFs from a ZIP
          </h2>
          {batchId ? (
            <BatchReview
              pid={pid}
              bid={batchId}
              records={records}
              onDone={() => {
                setBatchId(null);
                refresh();
              }}
            />
          ) : (
            <ZipDropzone
              pid={pid}
              onStarted={(id) => {
                setBatchId(id);
              }}
            />
          )}
        </section>
      )}

      <section aria-labelledby="records-heading" className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="records-heading" className="text-base font-semibold">
            Records at full text
          </h2>
          <div role="group" aria-label="Show" className="flex flex-wrap gap-1">
            {FILTERS.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={filter === option.value ? "secondary" : "ghost"}
                aria-pressed={filter === option.value}
                onClick={() => {
                  setFilter(option.value);
                }}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>
        {canScreen && (
          <p className="text-sm text-muted-foreground">
            Drop a PDF onto its record to add it, or open a record to find a free copy.
          </p>
        )}
        {isPending ? (
          <div className="grid gap-2" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-14 w-full" />
            ))}
          </div>
        ) : records.length === 0 ? (
          <p className="rounded-lg border border-dashed border-input p-8 text-center text-sm text-muted-foreground">
            No record has reached full text yet. Records included at title and abstract appear here.
          </p>
        ) : shown.length === 0 ? (
          <p className="rounded-lg border border-dashed border-input p-8 text-center text-sm text-muted-foreground">
            None here.
          </p>
        ) : (
          <RecordList
            pid={pid}
            records={shown}
            canScreen={canScreen}
            onOpen={setOpen}
            onUploaded={refresh}
          />
        )}
      </section>

      <Sheet
        open={open !== null}
        onOpenChange={(value) => {
          if (!value) setOpen(null);
        }}
      >
        <SheetContent
          side={isMobile ? "bottom" : "right"}
          className={cn("overflow-y-auto sm:max-w-3xl", isMobile && "max-h-[92dvh]")}
        >
          <SheetHeader>
            <SheetTitle>{open?.title ?? "Untitled record"}</SheetTitle>
            <SheetDescription>
              {[open?.first_author, open?.year, open?.journal].filter(Boolean).join(" · ")}
            </SheetDescription>
          </SheetHeader>
          {open && (
            <div className="px-4 pb-6">
              <FullTextPanel
                pid={pid}
                record={open}
                matchers={[]}
                canScreen={canScreen}
                openAccess={Boolean(summary?.open_access)}
                onChange={refresh}
                onNotRetrievable={refresh}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums">{value.toLocaleString()}</dd>
    </div>
  );
}

function RecordList({
  pid,
  records,
  canScreen,
  onOpen,
  onUploaded,
}: {
  pid: string;
  records: FulltextRecord[];
  canScreen: boolean;
  onOpen: (record: FulltextRecord) => void;
  onUploaded: () => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  // The compiler cannot memoise a virtualiser's callbacks; that is the point of it.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: records.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });
  return (
    <>
      {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- a scrollable region has to be
          keyboard reachable (axe scrollable-region-focusable), which this rule forbids. */}
      <div
        ref={scroller}
        className="max-h-[60vh] overflow-auto rounded-lg border border-border"
        tabIndex={0}
        role="region"
        aria-label="List of records at full text"
      >
        {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
        <ul style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualizer.getVirtualItems().map((item) => {
            const record = records[item.index];
            if (!record) return null;
            return (
              <li
                key={record.id}
                className="absolute inset-x-0"
                style={{ transform: `translateY(${item.start}px)`, height: ROW_HEIGHT }}
              >
                <RecordRow
                  pid={pid}
                  record={record}
                  canScreen={canScreen}
                  onOpen={() => {
                    onOpen(record);
                  }}
                  onUploaded={onUploaded}
                />
              </li>
            );
          })}
        </ul>
      </div>
      <p className="text-xs text-muted-foreground">
        {records.length.toLocaleString()} record{records.length === 1 ? "" : "s"}
      </p>
    </>
  );
}

const STATE_LABEL: Record<Exclude<Filter, "all">, string> = {
  missing: "No PDF",
  scanning: "Being scanned",
  quarantined: "Quarantined",
  pdf: "PDF",
  not_retrievable: "Not retrievable",
};

function StateBadge({ record }: { record: FulltextRecord }) {
  const state = stateOf(record);
  const failed = record.fulltext?.scan_status === "error";
  const Icon =
    state === "pdf"
      ? CircleCheckIcon
      : state === "quarantined"
        ? ShieldAlertIcon
        : state === "scanning" && !failed
          ? LoaderCircleIcon
          : state === "not_retrievable"
            ? BanIcon
            : CircleDashedIcon;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
        state === "pdf" && "border-include/40 bg-include-muted",
        state === "quarantined" && "border-exclude/40 bg-exclude-muted",
        state === "scanning" && "border-maybe/40 bg-maybe-muted",
        (state === "missing" || state === "not_retrievable") && "border-border",
      )}
    >
      <Icon
        className={cn("size-3.5", state === "scanning" && !failed && "animate-spin")}
        aria-hidden="true"
      />
      {failed ? "Scan failed" : STATE_LABEL[state]}
    </span>
  );
}

function RecordRow({
  pid,
  record,
  canScreen,
  onOpen,
  onUploaded,
}: {
  pid: string;
  record: FulltextRecord;
  canScreen: boolean;
  onOpen: () => void;
  onUploaded: () => void;
}) {
  const [over, setOver] = useState(false);
  const inputId = useId();
  const state = stateOf(record);
  const upload = useMutation({
    mutationFn: (file: File) => uploadPdf(pid, record.id, file),
    onSuccess: () => {
      toast.success(`PDF added to “${record.title ?? "the record"}”.`);
      onUploaded();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const takesPdf = canScreen && (state === "missing" || state === "quarantined");

  return (
    <div
      className={cn(
        "flex h-full items-center gap-3 border-b border-border px-3",
        over && "bg-accent",
      )}
      onDragOver={(event) => {
        if (!takesPdf) return;
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => {
        setOver(false);
      }}
      onDrop={(event) => {
        if (!takesPdf) return;
        event.preventDefault();
        setOver(false);
        const file = event.dataTransfer.files[0];
        if (file) upload.mutate(file);
      }}
    >
      <button type="button" onClick={onOpen} className="grid min-w-0 flex-1 text-left">
        <span className="truncate text-sm font-medium">{record.title ?? "Untitled record"}</span>
        <span className="truncate text-xs text-muted-foreground">
          {[record.first_author, record.year, record.journal].filter(Boolean).join(" · ")}
        </span>
      </button>
      <StateBadge record={record} />
      {takesPdf && (
        <>
          <label
            htmlFor={inputId}
            className="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md hover:bg-accent"
            title="Add the PDF"
          >
            {upload.isPending ? (
              <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileUpIcon className="size-4" aria-hidden="true" />
            )}
            <span className="sr-only">Add the PDF for {record.title ?? "this record"}</span>
          </label>
          <input
            id={inputId}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            disabled={upload.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) upload.mutate(file);
            }}
          />
        </>
      )}
    </div>
  );
}

function ZipDropzone({ pid, onStarted }: { pid: string; onStarted: (id: string) => void }) {
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const id = useId();
  const upload = useMutation({
    mutationFn: (file: File) => uploadZip(pid, file),
    onSuccess: (batch) => {
      setProblem(null);
      onStarted(batch.id);
    },
    onError: (error) => {
      setProblem(errorMessage(error));
    },
  });
  const take = (file: File | undefined) => {
    if (file) upload.mutate(file);
  };
  return (
    <div className="grid gap-2">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => {
          setOver(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          take(event.dataTransfer.files[0]);
        }}
        className={cn(
          "grid justify-items-center gap-2 rounded-lg border border-dashed border-input p-6 text-center",
          over && "border-ring bg-accent",
        )}
      >
        <FileArchiveIcon className="size-6 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm">
          {upload.isPending ? "Uploading and checking the ZIP…" : "Drop a ZIP of PDFs here, or"}{" "}
          {!upload.isPending && (
            <label htmlFor={id} className="cursor-pointer font-medium underline underline-offset-2">
              choose one
            </label>
          )}
        </p>
        <input
          id={id}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          disabled={upload.isPending}
          onChange={(event) => {
            take(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <p className="max-w-prose text-xs text-muted-foreground">
          Name each file by DOI, PMID, PMCID or first author and year (for example{" "}
          <span className="font-mono">Smith 2019.pdf</span>). You check every match before any PDF
          is attached, and each one is scanned for viruses.
        </p>
      </div>
      {problem && (
        <p
          role="alert"
          className="rounded-lg border border-exclude/40 bg-exclude-muted p-3 text-sm"
        >
          {problem}
        </p>
      )}
    </div>
  );
}

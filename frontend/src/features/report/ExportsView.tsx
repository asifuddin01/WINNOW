import { useQuery } from "@tanstack/react-query";
import {
  ArchiveIcon,
  ClipboardListIcon,
  DownloadIcon,
  FileSpreadsheetIcon,
  LoaderIcon,
} from "lucide-react";
import { useId, useState, type ReactNode, type SyntheticEvent } from "react";

import {
  exportFileUrl,
  exportKeys,
  exportsQuery,
  requestExport,
  working,
  type ExportIn,
  type ExportJob,
} from "@/api/exports";
import { formsQuery } from "@/api/extraction";
import { facetsQuery } from "@/api/records";
import { SelectField } from "@/components/forms/SelectField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { fileSize, timeAgo } from "@/lib/format";

type Kind = "records" | "backup" | "extraction";
type RecordFormat = "csv" | "xlsx" | "ris" | "bibtex";

const FORMATS: { value: RecordFormat; label: string }[] = [
  { value: "csv", label: "CSV" },
  { value: "xlsx", label: "Excel (XLSX)" },
  { value: "ris", label: "RIS (EndNote, Zotero, Mendeley)" },
  { value: "bibtex", label: "BibTeX" },
];

const ANY = "any";

export function ExportsView({ pid, isOwner }: { pid: string; isOwner: boolean }) {
  const { data: jobs, isPending } = useQuery(exportsQuery(pid));
  return (
    <div className="grid gap-6">
      <ExportForm pid={pid} isOwner={isOwner} />
      <section aria-labelledby="my-exports" className="grid gap-3">
        <div>
          <h2 id="my-exports" className="text-lg font-medium">
            Your files
          </h2>
          <p className="text-sm text-muted-foreground">
            Only you can download them, for a day after they are made.
          </p>
        </div>
        {isPending ? (
          <Skeleton className="h-20 w-full rounded-xl" aria-busy="true" />
        ) : jobs && jobs.length > 0 ? (
          <ul className="grid gap-2" aria-live="polite">
            {jobs.map((job) => (
              <li key={job.id}>
                <JobRow pid={pid} job={job} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
            Nothing yet. Files you make appear here.
          </p>
        )}
      </section>
    </div>
  );
}

function ExportForm({ pid, isOwner }: { pid: string; isOwner: boolean }) {
  const id = useId();
  const { data: facets } = useQuery(facetsQuery(pid));
  const [kind, setKind] = useState<Kind>("records");
  const { data: forms } = useQuery(formsQuery(pid));
  const published = (forms ?? []).filter((form) => form.published);
  const [formId, setFormId] = useState<string | null>(null);
  const [layout, setLayout] = useState<"wide" | "long">("wide");
  const [which, setWhich] = useState<"final" | "all">("final");
  const [sheet, setSheet] = useState<"csv" | "xlsx">("csv");
  const [format, setFormat] = useState<RecordFormat>("csv");
  const [status, setStatus] = useState<string>(ANY);
  const [fullText, setFullText] = useState<string>(ANY);
  const [duplicates, setDuplicates] = useState(false);

  const make = useProjectMutation((body: ExportIn) => requestExport(pid, body), {
    invalidate: [exportKeys.all(pid)],
    success: "Making your file. It appears below when it is ready.",
  });

  const onSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    const form = formId ?? published.at(-1)?.id;
    make.mutate(
      kind === "backup"
        ? { kind: "backup", format: "zip" }
        : kind === "extraction" && form
          ? { kind: "extraction", format: sheet, extraction: { form_id: form, layout, which } }
          : {
              kind: "records",
              format,
              filters: {
                q: "",
                status:
                  status === ANY ? null : (status as NonNullable<ExportIn["filters"]>["status"]),
                full_text:
                  fullText === ANY
                    ? null
                    : (fullText as NonNullable<ExportIn["filters"]>["full_text"]),
                duplicates,
              },
            },
    );
  };

  const statusOptions = [
    { value: ANY, label: "Any" },
    ...(facets?.title_abstract ?? []).map((count) => ({
      value: count.value,
      label: `${count.label} (${count.count.toLocaleString()})`,
    })),
  ];
  const fullTextOptions = [
    { value: ANY, label: "Any" },
    ...(facets?.full_text ?? []).map((count) => ({
      value: count.value,
      label: `${count.label} (${count.count.toLocaleString()})`,
    })),
  ];

  return (
    <form
      onSubmit={onSubmit}
      className="grid gap-5 rounded-xl border border-border bg-card p-5"
      aria-labelledby={`${id}-title`}
    >
      <h2 id={`${id}-title`} className="text-lg font-medium">
        Make a file
      </h2>
      <fieldset className="grid gap-2 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">What to export</legend>
        <Choice
          name={`${id}-kind`}
          checked={kind === "records"}
          onChange={() => {
            setKind("records");
          }}
          icon={<FileSpreadsheetIcon aria-hidden="true" className="size-5" />}
          title="Records"
          detail="The records and your review's decisions, reasons and labels, as the records table shows them."
        />
        {published.length > 0 && (
          <Choice
            name={`${id}-kind`}
            checked={kind === "extraction"}
            onChange={() => {
              setKind("extraction");
            }}
            icon={<ClipboardListIcon aria-hidden="true" className="size-5" />}
            title="Extracted data"
            detail="One form's data, long (one row per value) or wide (one row per study), for R, Stata or RevMan."
          />
        )}
        {isOwner && (
          <Choice
            name={`${id}-kind`}
            checked={kind === "backup"}
            onChange={() => {
              setKind("backup");
            }}
            icon={<ArchiveIcon aria-hidden="true" className="size-5" />}
            title="Full backup"
            detail="Everything in the review, with its PDFs, to restore here or on another Winnow."
          />
        )}
      </fieldset>

      {kind === "records" ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <SelectField label="Format" value={format} options={FORMATS} onChange={setFormat} />
          <SelectField
            label="Title and abstract"
            value={status}
            options={statusOptions}
            onChange={setStatus}
          />
          <SelectField
            label="Full text"
            value={fullText}
            options={fullTextOptions}
            onChange={setFullText}
          />
          <label className="flex items-center gap-2 text-sm sm:col-span-3">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={duplicates}
              onChange={(event) => {
                setDuplicates(event.target.checked);
              }}
            />
            Include records merged as duplicates, with the record each was merged into
          </label>
        </div>
      ) : kind === "extraction" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Form"
            value={formId ?? published.at(-1)?.id ?? ""}
            options={published.map((form) => ({
              value: form.id,
              label: `${form.name}, version ${form.version}`,
            }))}
            onChange={setFormId}
          />
          <SelectField
            label="Format"
            value={sheet}
            options={[
              { value: "csv", label: "CSV" },
              { value: "xlsx", label: "Excel (XLSX)" },
            ]}
            onChange={setSheet}
          />
          <SelectField
            label="Layout"
            value={layout}
            options={[
              { value: "wide", label: "Wide: a row per study (RevMan, spreadsheets)" },
              { value: "long", label: "Long: a row per value (R, Stata)" },
            ]}
            onChange={setLayout}
          />
          <SelectField
            label="Which data"
            value={which}
            options={[
              { value: "final", label: "Final: the consensus, or the only extraction" },
              { value: "all", label: "All: every extractor and the consensus" },
            ]}
            onChange={setWhich}
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          A ZIP of every record, decision, note, label, full text, highlight, risk-of-bias
          assessment and the review&apos;s history, with the names and email addresses of the people
          who did the work. Keep it somewhere safe. PDFs still waiting for the virus scanner are
          left out.
        </p>
      )}

      <div>
        <Button type="submit" disabled={make.isPending}>
          {make.isPending ? "Asking…" : kind === "backup" ? "Make a backup" : "Make the file"}
        </Button>
      </div>
    </form>
  );
}

function Choice({
  name,
  checked,
  onChange,
  icon,
  title,
  detail,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  icon: ReactNode;
  title: string;
  detail: string;
}) {
  return (
    <label className="flex cursor-pointer gap-3 rounded-lg border border-border p-3 has-checked:border-primary has-checked:bg-primary/5 has-focus-visible:ring-3 has-focus-visible:ring-ring/50">
      <input type="radio" name={name} checked={checked} onChange={onChange} className="sr-only" />
      <span className="mt-0.5 text-muted-foreground">{icon}</span>
      <span className="grid gap-0.5">
        <span className="text-sm font-medium">
          {title}
          {checked && <span className="sr-only"> (selected)</span>}
        </span>
        <span className="text-xs text-muted-foreground">{detail}</span>
      </span>
    </label>
  );
}

const FORMAT_NAMES: Record<ExportJob["format"], string> = {
  csv: "CSV",
  xlsx: "XLSX",
  ris: "RIS",
  bibtex: "BibTeX",
  zip: "ZIP",
};

const STATUS_WORDS: Record<ExportJob["status"], string> = {
  queued: "Waiting",
  running: "Being made",
  ready: "Ready",
  failed: "Failed",
};

function JobRow({ pid, job }: { pid: string; job: ExportJob }) {
  const what =
    job.kind === "backup"
      ? "Full backup"
      : `${job.kind === "extraction" ? "Extracted data" : "Records"} (${FORMAT_NAMES[job.format]})`;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3">
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="truncate text-sm font-medium">{job.filename ?? what}</p>
        <p className="text-xs text-muted-foreground">
          {what} · asked {timeAgo(job.created_at)}
          {job.rows !== null && ` · ${job.rows.toLocaleString()} rows`}
          {job.size_bytes !== null && ` · ${fileSize(job.size_bytes)}`}
        </p>
        {job.problem && <p className="text-sm text-destructive">{job.problem}</p>}
      </div>
      {working(job.status) ? (
        <Badge variant="secondary">
          <LoaderIcon className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {STATUS_WORDS[job.status]}
        </Badge>
      ) : job.status === "ready" ? (
        <Button asChild size="sm">
          <a href={exportFileUrl(pid, job.id)} download={job.filename ?? undefined}>
            <DownloadIcon aria-hidden="true" /> Download
            <span className="sr-only"> {job.filename}</span>
          </a>
        </Button>
      ) : (
        <Badge variant="destructive">{STATUS_WORDS[job.status]}</Badge>
      )}
    </div>
  );
}

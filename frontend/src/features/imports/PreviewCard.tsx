import { useQuery } from "@tanstack/react-query";
import { TriangleAlertIcon } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import { importPreviewQuery, type ImportBatch } from "@/api/imports";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** The fields a CSV column can be mapped onto; "—" leaves the column out. */
const FIELDS = [
  { value: "", label: "— not imported —" },
  { value: "title", label: "Title" },
  { value: "abstract", label: "Abstract" },
  { value: "authors", label: "Authors" },
  { value: "year", label: "Year" },
  { value: "journal", label: "Journal" },
  { value: "volume", label: "Volume" },
  { value: "issue", label: "Issue" },
  { value: "pages", label: "Pages" },
  { value: "page_start", label: "Page (start)" },
  { value: "page_end", label: "Page (end)" },
  { value: "doi", label: "DOI" },
  { value: "pmid", label: "PubMed id" },
  { value: "url", label: "Link" },
  { value: "keywords", label: "Keywords" },
  { value: "language", label: "Language" },
  { value: "publication_type", label: "Publication type" },
  { value: "isbn", label: "ISSN or ISBN" },
];

interface PreviewCardProps {
  pid: string;
  batch: ImportBatch;
  mapping?: Record<string, string>;
  onMappingChange: (mapping: Record<string, string>) => void;
  /** With several files at once, each one opens on request rather than all at once. */
  collapsed?: boolean;
}

/** Guide 8.3: one file as Winnow read it — the first records, and CSV's column mapping. */
export function PreviewCard({
  pid,
  batch,
  mapping,
  onMappingChange,
  collapsed = false,
}: PreviewCardProps) {
  const [open, setOpen] = useState(!collapsed);
  const {
    data: preview,
    isPending,
    error,
  } = useQuery({
    ...importPreviewQuery(pid, batch.id),
    enabled: open,
  });

  const header = (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="secondary">{batch.file_format.replace("_", " ")}</Badge>
      <span className="min-w-0 flex-1 truncate font-medium">{batch.filename}</span>
      <span className="text-muted-foreground">
        {(batch.size_bytes / 1024).toFixed(0)} KB · {batch.database_name}
      </span>
      {collapsed && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-expanded={open}
          onClick={() => {
            setOpen((current) => !current);
          }}
        >
          {open ? "Hide" : "Check"}
        </Button>
      )}
    </div>
  );

  if (!open) return header;
  if (isPending) {
    return (
      <div className="grid gap-3">
        {header}
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="grid gap-3">
        {header}
        <FormAlert>{errorMessage(error)}</FormAlert>
      </div>
    );
  }

  const columns = preview.columns ?? [];
  const chosen = mapping ?? preview.suggested_mapping ?? {};

  return (
    <div className="grid gap-4">
      {header}

      {columns.length > 0 && (
        <section aria-labelledby={`mapping-${batch.id}`} className="grid gap-3">
          <div>
            <h3 id={`mapping-${batch.id}`} className="text-sm font-semibold">
              Which column holds what?
            </h3>
            <p className="text-xs text-muted-foreground">
              Winnow has guessed from the headings. Change anything it got wrong.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {columns.map((column) => (
              <SelectField
                key={column}
                label={column}
                value={chosen[column] ?? ""}
                options={FIELDS}
                onChange={(field) => {
                  // A column with no field chosen is simply left out of the mapping.
                  onMappingChange(
                    Object.fromEntries(
                      Object.entries({ ...chosen, [column]: field }).filter(([, value]) => value),
                    ),
                  );
                }}
              />
            ))}
          </div>
        </section>
      )}

      <section aria-labelledby={`first-records-${batch.id}`} className="grid gap-2">
        <h3 id={`first-records-${batch.id}`} className="text-sm font-semibold">
          The first records Winnow read
        </h3>
        {preview.records.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            None of the records could be read. Check the column mapping, or the file.
          </p>
        ) : (
          <ul className="grid gap-2">
            {preview.records.map((record, index) => (
              <li key={index} className="rounded-lg border border-border bg-background p-3">
                <p className="text-sm font-medium">{record.title ?? "(no title)"}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {[record.authors.slice(0, 3).join("; "), record.year, record.journal]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                {record.doi && <p className="mt-0.5 font-mono text-xs">{record.doi}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {preview.problems.length > 0 && (
        <p className="flex items-start gap-2 text-sm text-maybe">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {preview.problems.length} entr{preview.problems.length === 1 ? "y" : "ies"} near the
            start could not be read ({preview.problems[0]?.reason}). They are listed after the
            import, and the rest still come in.
          </span>
        </p>
      )}
    </div>
  );
}

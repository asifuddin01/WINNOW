import { useMutation } from "@tanstack/react-query";
import { FileUpIcon, UploadIcon, XIcon } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { errorMessage } from "@/api/client";
import { uploadImports, type ImportUpload } from "@/api/imports";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Button } from "@/components/ui/button";
import { DATABASE_OPTIONS, databaseFor } from "@/features/imports/databases";
import { cn } from "@/lib/utils";

const ACCEPTED = ".ris,.bib,.bibtex,.nbib,.xml,.csv,.tsv,.txt";

interface Chosen {
  file: File;
  database: string;
}

export function UploadCard({
  pid,
  limit,
  onUploaded,
}: {
  pid: string;
  /** How many files this instance takes at once (guide 8.3). */
  limit: number;
  onUploaded: (result: ImportUpload) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<Chosen[]>([]);
  const [searchDate, setSearchDate] = useState("");
  const [searchString, setSearchString] = useState("");
  const [dragging, setDragging] = useState(false);
  const [tooMany, setTooMany] = useState(false);

  const add = (files: FileList | null) => {
    if (!files?.length) return;
    const picked = [...files].map((file) => ({ file, database: databaseFor(file.name) }));
    setChosen((current) => {
      // The same file chosen twice is one file; the picker gives no ids of its own.
      const seen = new Set(current.map(({ file }) => `${file.name}:${file.size}`));
      const merged = [
        ...current,
        ...picked.filter(({ file }) => !seen.has(`${file.name}:${file.size}`)),
      ];
      setTooMany(merged.length > limit);
      return merged.slice(0, limit);
    });
  };

  const upload = useMutation({
    mutationFn: (files: Chosen[]) =>
      uploadImports(pid, {
        files: files.map(({ file, database }) => ({ file, database_name: database })),
        search_date: searchDate || undefined,
        search_string: searchString || undefined,
      }),
    onSuccess: (result) => {
      setChosen([]);
      onUploaded(result);
    },
  });

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    add(event.dataTransfer.files);
  };

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen.length > 0) upload.mutate(chosen);
      }}
    >
      {upload.isError && <FormAlert>{errorMessage(upload.error)}</FormAlert>}
      {tooMany && (
        <FormAlert>
          Winnow takes {limit} files at a time. The first {limit} are ready; upload the rest after
          these.
        </FormAlert>
      )}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={onDrop}
        className={cn(
          "grid justify-items-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-input",
        )}
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <FileUpIcon className="size-6" aria-hidden="true" />
        </span>
        <p className="text-sm font-medium">Drop your search exports here, or choose files</p>
        <p className="max-w-md text-xs text-muted-foreground">
          Up to {limit} files at once. RIS, BibTeX, PubMed NBIB, PubMed XML, EndNote XML or CSV —
          Winnow works out which one each file is from the file itself.
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPTED}
          className="sr-only"
          aria-label="Search export files"
          onChange={(event) => {
            add(event.target.files);
            event.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            input.current?.click();
          }}
        >
          Choose files
        </Button>
      </div>

      {chosen.length > 0 && (
        <section aria-labelledby="chosen-files" className="grid gap-2">
          <h3 id="chosen-files" className="text-sm font-semibold">
            {chosen.length} file{chosen.length === 1 ? "" : "s"} ready
          </h3>
          <p className="text-xs text-muted-foreground">
            Winnow has guessed the database from each file name. Correct any it got wrong — PRISMA
            reports the results per database.
          </p>
          <ul className="grid gap-2">
            {chosen.map(({ file, database }, index) => (
              <li
                key={`${file.name}:${file.size}`}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-2.5"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{file.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(0)} KB
                  </span>
                </span>
                <SelectField
                  label={`Database for ${file.name}`}
                  hideLabel
                  className="w-48"
                  value={database}
                  options={DATABASE_OPTIONS}
                  onChange={(next) => {
                    setChosen((current) =>
                      current.map((item, position) =>
                        position === index ? { ...item, database: next } : item,
                      ),
                    );
                  }}
                />
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => {
                    setChosen((current) => current.filter((_, position) => position !== index));
                    setTooMany(false);
                  }}
                >
                  <XIcon aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Search date"
          type="date"
          hint="Optional. PRISMA reports when each database was searched."
          value={searchDate}
          onChange={(event) => {
            setSearchDate(event.target.value);
          }}
        />
      </div>
      <TextareaField
        label="Search string"
        rows={2}
        hint="Optional, but it is what the methods section will need later. It is kept with every file in this upload."
        value={searchString}
        onChange={(event) => {
          setSearchString(event.target.value);
        }}
      />
      <Button
        type="submit"
        className="justify-self-start"
        disabled={chosen.length === 0 || upload.isPending}
      >
        <UploadIcon aria-hidden="true" />
        {upload.isPending
          ? `Uploading ${chosen.length} file${chosen.length === 1 ? "" : "s"}…`
          : `Upload and preview${chosen.length > 1 ? ` ${chosen.length} files` : ""}`}
      </Button>
    </form>
  );
}

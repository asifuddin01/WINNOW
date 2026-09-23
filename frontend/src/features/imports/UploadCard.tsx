import { useMutation } from "@tanstack/react-query";
import { FileUpIcon, UploadIcon } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { errorMessage } from "@/api/client";
import { uploadImport, type ImportBatch } from "@/api/imports";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The databases a search usually comes from; PRISMA-S asks which one (guide 8.3). */
const DATABASES = [
  "PubMed",
  "Embase",
  "Scopus",
  "Web of Science",
  "CINAHL",
  "Cochrane Library",
  "PsycINFO",
  "Other",
].map((name) => ({ value: name, label: name }));

const ACCEPTED = ".ris,.bib,.bibtex,.nbib,.xml,.csv,.tsv,.txt";

export function UploadCard({
  pid,
  onUploaded,
}: {
  pid: string;
  onUploaded: (batch: ImportBatch) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [database, setDatabase] = useState("PubMed");
  const [searchDate, setSearchDate] = useState("");
  const [searchString, setSearchString] = useState("");
  const [dragging, setDragging] = useState(false);

  const upload = useMutation({
    mutationFn: (chosen: File) =>
      uploadImport(pid, {
        file: chosen,
        database_name: database,
        source_name: `${database} ${searchDate || new Date().toISOString().slice(0, 10)}`,
        search_date: searchDate || undefined,
        search_string: searchString || undefined,
      }),
    onSuccess: (batch) => {
      setFile(null);
      onUploaded(batch);
    },
  });

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  };

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (file) upload.mutate(file);
      }}
    >
      {upload.isError && <FormAlert>{errorMessage(upload.error)}</FormAlert>}
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
        <p className="text-sm font-medium">
          {file ? file.name : "Drop a search export here, or choose a file"}
        </p>
        <p className="max-w-md text-xs text-muted-foreground">
          RIS, BibTeX, PubMed NBIB, PubMed XML, EndNote XML or CSV. Winnow works out which one it is
          from the file itself.
        </p>
        <input
          ref={input}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          aria-label="Search export file"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
          }}
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            input.current?.click();
          }}
        >
          Choose a file
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Database searched"
          value={database}
          options={DATABASES}
          onChange={setDatabase}
        />
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
        hint="Optional, but it is what the methods section will need later."
        value={searchString}
        onChange={(event) => {
          setSearchString(event.target.value);
        }}
      />
      <Button type="submit" className="justify-self-start" disabled={!file || upload.isPending}>
        <UploadIcon aria-hidden="true" />
        {upload.isPending ? "Uploading…" : "Upload and preview"}
      </Button>
    </form>
  );
}

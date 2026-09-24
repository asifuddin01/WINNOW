import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BanIcon,
  DownloadIcon,
  FileSearchIcon,
  FileUpIcon,
  HighlighterIcon,
  LoaderCircleIcon,
  ShieldAlertIcon,
  Trash2Icon,
  Undo2Icon,
} from "lucide-react";
import { lazy, Suspense, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import {
  addAnnotation,
  annotationsQuery,
  deleteAnnotation,
  downloadLink,
  fetchOpenAccess,
  findOpenAccess,
  fulltextKeys,
  markNotRetrievable,
  pdfQuery,
  readable,
  recordFulltextQuery,
  unmarkNotRetrievable,
  updateAnnotation,
  uploadPdf,
  type Annotation,
  type AnnotationColor,
  type FulltextOut,
  type OpenAccessFinds,
  type RecordFulltext,
} from "@/api/fulltext";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ANNOTATION_FILL, ANNOTATION_NAMES } from "@/features/fulltext/colors";
import type { NewHighlight } from "@/features/fulltext/PdfViewer";
import type { Matcher } from "@/features/screening/highlight";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";

const PdfViewer = lazy(() => import("@/features/fulltext/PdfViewer"));

interface Props {
  pid: string;
  record: { id: string; title: string | null; doi: string | null; pmcid?: string | null };
  matchers: Matcher[];
  /** May add, replace and annotate PDFs, and mark them not retrievable. */
  canScreen: boolean;
  openAccess: boolean;
  /** The PDF changed (for the screening queue to keep its copy of the record current). */
  onChange?: (fulltext: FulltextOut | null) => void;
  /** Marked not retrievable: the record leaves the full-text queue. */
  onNotRetrievable?: () => void;
}

/**
 * A record's full text (guide 8.8): its PDF in the viewer once the virus scanner has
 * cleared it, or the ways to get one — upload, a free copy, or "not retrievable".
 */
export function FullTextPanel({
  pid,
  record,
  matchers,
  canScreen,
  openAccess,
  onChange,
  onNotRetrievable,
}: Props) {
  const queryClient = useQueryClient();
  const { data: state, isPending } = useQuery(recordFulltextQuery(pid, record.id));
  const fulltext = state?.fulltext ?? null;

  const refresh = (next?: RecordFulltext) => {
    if (next) queryClient.setQueryData(fulltextKeys.record(pid, record.id), next);
    void queryClient.invalidateQueries({ queryKey: fulltextKeys.record(pid, record.id) });
    void queryClient.invalidateQueries({ queryKey: fulltextKeys.summary(pid) });
    void queryClient.invalidateQueries({ queryKey: fulltextKeys.records(pid) });
  };

  const attached = (added: FulltextOut) => {
    refresh({ fulltext: added, not_retrievable: false });
    onChange?.(added);
  };

  const upload = useMutation({
    mutationFn: (file: File) => uploadPdf(pid, record.id, file),
    onSuccess: (added) => {
      attached(added);
      toast.success("PDF added. It opens as soon as the virus scan is done.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (isPending) return <Skeleton className="h-64 w-full" />;
  if (!state) return null;

  if (state.not_retrievable) {
    return (
      <NotRetrievableNotice
        pid={pid}
        rid={record.id}
        note={state.not_retrievable_note ?? null}
        canScreen={canScreen}
        onUndone={refresh}
      />
    );
  }

  if (fulltext && readable(fulltext.scan_status)) {
    return (
      <ReadablePdf
        pid={pid}
        rid={record.id}
        label={record.title ?? "Full text"}
        fulltext={fulltext}
        matchers={matchers}
        canScreen={canScreen}
        onReplace={(file) => {
          upload.mutate(file);
        }}
        replacing={upload.isPending}
      />
    );
  }

  return (
    <div className="grid gap-4">
      {fulltext?.scan_status === "pending" && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 p-4 text-sm"
        >
          <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
          Checking {fulltext.filename} for viruses. It opens here as soon as it is cleared.
        </p>
      )}
      {fulltext?.scan_status === "infected" && (
        <div
          role="alert"
          className="flex gap-3 rounded-lg border border-exclude/40 bg-exclude-muted p-4 text-sm"
        >
          <ShieldAlertIcon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <div className="grid gap-1">
            <p className="font-semibold">This PDF was quarantined.</p>
            <p>
              The virus scanner flagged {fulltext.filename}. Nobody can open or download it, and the
              review&apos;s owners and admins have been told. Add a fresh copy from the publisher
              instead.
            </p>
          </div>
        </div>
      )}
      {fulltext?.scan_status === "error" && (
        <p role="alert" className="rounded-lg border border-maybe/40 bg-maybe-muted p-4 text-sm">
          The virus scanner could not check {fulltext.filename}, so it stays closed. Try adding it
          again in a few minutes.
        </p>
      )}
      {canScreen && fulltext?.scan_status !== "pending" && (
        <>
          <PdfDropzone
            busy={upload.isPending}
            onFile={(file) => {
              upload.mutate(file);
            }}
          />
          <div className="flex flex-wrap gap-2">
            {openAccess && (
              <OpenAccessFinder
                pid={pid}
                rid={record.id}
                disabled={!record.doi && !record.pmcid}
                onFetched={attached}
              />
            )}
            <NotRetrievableButton
              pid={pid}
              rid={record.id}
              onMarked={(next) => {
                refresh(next);
                onNotRetrievable?.();
              }}
            />
          </div>
        </>
      )}
      {!canScreen && !fulltext && (
        <p className="rounded-lg border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
          No PDF has been added for this record yet.
        </p>
      )}
    </div>
  );
}

function ReadablePdf({
  pid,
  rid,
  label,
  fulltext,
  matchers,
  canScreen,
  onReplace,
  replacing,
}: {
  pid: string;
  rid: string;
  label: string;
  fulltext: FulltextOut;
  matchers: Matcher[];
  canScreen: boolean;
  onReplace: (file: File) => void;
  replacing: boolean;
}) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const [listOpen, setListOpen] = useState(false);
  const [jump, setJump] = useState<{ page: number; key: number } | null>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const pdf = useQuery(pdfQuery(pid, rid, fulltext.id));
  const { data: annotations = [] } = useQuery(annotationsQuery(pid, fulltext.id));
  const annotationsKey = fulltextKeys.annotations(pid, fulltext.id);

  const create = useMutation({
    mutationFn: (highlight: NewHighlight) =>
      addAnnotation(pid, fulltext.id, {
        page: highlight.page,
        rects: highlight.rects,
        quote: highlight.quote,
        color: highlight.color,
      }),
    onSuccess: (annotation) => {
      queryClient.setQueryData<Annotation[]>(annotationsKey, (was = []) => [...was, annotation]);
      toast.success("Highlighted. Add a comment to it under Highlights.", {
        action: {
          label: "Highlights",
          onClick: () => {
            setListOpen(true);
          },
        },
      });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const download = async () => {
    try {
      const url = await downloadLink(pid, rid);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.rel = "noopener";
      anchor.click();
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const actions = (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8"
        onClick={() => {
          setListOpen(true);
        }}
      >
        <HighlighterIcon aria-hidden="true" />
        <span className={cn(isMobile && "sr-only")}>Highlights</span>
        <span className="tabular-nums">({annotations.length})</span>
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label="Download the PDF"
        onClick={() => void download()}
      >
        <DownloadIcon aria-hidden="true" />
      </Button>
      {canScreen && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Replace the PDF"
            disabled={replacing}
            onClick={() => replaceRef.current?.click()}
          >
            <FileUpIcon aria-hidden="true" />
          </Button>
          <input
            ref={replaceRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) onReplace(file);
            }}
          />
        </>
      )}
    </>
  );

  return (
    <section aria-label="Full text" className="grid gap-2">
      {fulltext.scan_status === "skipped" && (
        <p className="text-xs text-muted-foreground">
          This Winnow runs without a virus scanner, so this PDF was not scanned.
        </p>
      )}
      {pdf.isError ? (
        <p role="alert" className="rounded-lg border border-border p-4 text-sm">
          The PDF could not be loaded: {errorMessage(pdf.error)}{" "}
          <Button variant="link" className="h-auto p-0" onClick={() => void pdf.refetch()}>
            Try again
          </Button>
        </p>
      ) : pdf.data ? (
        <Suspense fallback={<Skeleton className="h-[70dvh] w-full" />}>
          <PdfViewer
            data={pdf.data}
            label={label}
            matchers={matchers}
            annotations={annotations}
            canAnnotate={canScreen}
            onHighlight={(highlight) => {
              create.mutate(highlight);
            }}
            jump={jump}
            actions={actions}
          />
        </Suspense>
      ) : (
        <Skeleton className="h-[70dvh] w-full" />
      )}
      <Sheet open={listOpen} onOpenChange={setListOpen}>
        <SheetContent
          side={isMobile ? "bottom" : "right"}
          className={cn("overflow-y-auto", isMobile && "max-h-[85dvh]")}
        >
          <SheetHeader>
            <SheetTitle>Highlights</SheetTitle>
            <SheetDescription>
              Select text in the PDF to highlight it. Choose one here to go to its page.
            </SheetDescription>
          </SheetHeader>
          <HighlightList
            pid={pid}
            fid={fulltext.id}
            annotations={annotations}
            onGo={(page) => {
              setJump((was) => ({ page, key: (was?.key ?? 0) + 1 }));
              if (isMobile) setListOpen(false);
            }}
          />
        </SheetContent>
      </Sheet>
    </section>
  );
}

function HighlightList({
  pid,
  fid,
  annotations,
  onGo,
}: {
  pid: string;
  fid: string;
  annotations: Annotation[];
  onGo: (page: number) => void;
}) {
  const queryClient = useQueryClient();
  const key = fulltextKeys.annotations(pid, fid);
  const save = useMutation({
    mutationFn: ({ id, comment }: { id: string; comment: string | null }) =>
      updateAnnotation(pid, fid, id, { comment }),
    onSuccess: (saved) => {
      queryClient.setQueryData<Annotation[]>(key, (was = []) =>
        was.map((item) => (item.id === saved.id ? saved : item)),
      );
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteAnnotation(pid, fid, id),
    onSuccess: (_, id) => {
      queryClient.setQueryData<Annotation[]>(key, (was = []) =>
        was.filter((item) => item.id !== id),
      );
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (annotations.length === 0) {
    return (
      <p className="px-4 pb-6 text-sm text-muted-foreground">
        No highlights yet. Select a sentence in the PDF, then choose a colour.
      </p>
    );
  }
  return (
    <ol className="grid gap-3 px-4 pb-6">
      {annotations.map((annotation) => (
        <li key={annotation.id} className="grid gap-2 rounded-lg border border-border p-3">
          <button
            type="button"
            className="grid gap-1 text-left"
            onClick={() => {
              onGo(annotation.page);
            }}
          >
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              <span
                className={cn(
                  "size-3 rounded-full border border-black/20",
                  ANNOTATION_FILL[annotation.color as AnnotationColor],
                )}
                aria-hidden="true"
              />
              {ANNOTATION_NAMES[annotation.color as AnnotationColor]} · page {annotation.page}
              {annotation.mine ? "" : ` · ${annotation.author}`}
            </span>
            {annotation.quote && <q className="line-clamp-4 text-sm italic">{annotation.quote}</q>}
          </button>
          {annotation.mine ? (
            <CommentEditor
              initial={annotation.comment ?? ""}
              saving={save.isPending}
              onSave={(comment) => {
                save.mutate({ id: annotation.id, comment: comment || null });
              }}
              onDelete={() => {
                remove.mutate(annotation.id);
              }}
            />
          ) : (
            annotation.comment && (
              <p className="text-sm whitespace-pre-line">{annotation.comment}</p>
            )
          )}
        </li>
      ))}
    </ol>
  );
}

function CommentEditor({
  initial,
  saving,
  onSave,
  onDelete,
}: {
  initial: string;
  saving: boolean;
  onSave: (comment: string) => void;
  onDelete: () => void;
}) {
  const [text, setText] = useState(initial);
  const id = useId();
  return (
    <form
      className="grid gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(text.trim());
      }}
    >
      <label htmlFor={id} className="sr-only">
        Comment
      </label>
      <Textarea
        id={id}
        value={text}
        rows={2}
        placeholder="Add a comment"
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      <div className="flex justify-between gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDelete}>
          <Trash2Icon aria-hidden="true" /> Delete
        </Button>
        <Button type="submit" size="sm" variant="outline" disabled={saving || text === initial}>
          Save comment
        </Button>
      </div>
    </form>
  );
}

export function PdfDropzone({ busy, onFile }: { busy: boolean; onFile: (file: File) => void }) {
  const [over, setOver] = useState(false);
  const id = useId();
  return (
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
        const file = event.dataTransfer.files[0];
        if (file) onFile(file);
      }}
      className={cn(
        "grid justify-items-center gap-2 rounded-lg border border-dashed border-input p-6 text-center",
        over && "border-ring bg-accent",
      )}
    >
      <FileUpIcon className="size-6 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm">
        {busy ? "Uploading…" : "Drop the PDF here, or"}{" "}
        {!busy && (
          <label htmlFor={id} className="cursor-pointer font-medium underline underline-offset-2">
            choose a file
          </label>
        )}
      </p>
      <input
        id={id}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
      <p className="text-xs text-muted-foreground">
        It is scanned for viruses before anyone can open it.
      </p>
    </div>
  );
}

function OpenAccessFinder({
  pid,
  rid,
  disabled,
  onFetched,
}: {
  pid: string;
  rid: string;
  disabled: boolean;
  onFetched: (added: FulltextOut) => void;
}) {
  const [finds, setFinds] = useState<OpenAccessFinds | null>(null);
  const find = useMutation({
    mutationFn: () => findOpenAccess(pid, rid),
    onSuccess: setFinds,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const fetchCopy = useMutation({
    mutationFn: (candidate: string) => fetchOpenAccess(pid, rid, candidate),
    onSuccess: (added) => {
      toast.success("Free copy added. It opens as soon as the virus scan is done.");
      setFinds(null);
      onFetched(added);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="grid gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled || find.isPending}
        title={disabled ? "This record has no DOI or PMCID to look it up by." : undefined}
        onClick={() => {
          find.mutate();
        }}
      >
        {find.isPending ? (
          <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
        ) : (
          <FileSearchIcon aria-hidden="true" />
        )}
        Find free full text
      </Button>
      {finds && (
        <div role="status" className="grid gap-2 text-sm">
          {finds.candidates.length === 0 ? (
            <p className="text-muted-foreground">{finds.note ?? "No free copy was found."}</p>
          ) : (
            <ul className="grid gap-2">
              {finds.candidates.map((candidate) => (
                <li
                  key={candidate.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-2"
                >
                  <span>
                    <span className="font-medium">{candidate.host}</span>
                    <span className="text-muted-foreground">
                      {" · "}
                      {candidate.source === "pmc" ? "PubMed Central" : "via Unpaywall"}
                      {candidate.version ? ` · ${versionName(candidate.version)}` : ""}
                      {candidate.license ? ` · ${candidate.license}` : ""}
                    </span>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    disabled={fetchCopy.isPending}
                    onClick={() => {
                      fetchCopy.mutate(candidate.id);
                    }}
                  >
                    Get this copy
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function versionName(version: string) {
  if (version === "publishedVersion") return "published version";
  if (version === "acceptedVersion") return "accepted manuscript";
  if (version === "submittedVersion") return "preprint";
  return version;
}

function NotRetrievableButton({
  pid,
  rid,
  onMarked,
}: {
  pid: string;
  rid: string;
  onMarked: (state: RecordFulltext) => void;
}) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const id = useId();
  const mark = useMutation({
    mutationFn: () => markNotRetrievable(pid, rid, note.trim() || null),
    onSuccess: (state) => {
      toast.success("Marked not retrievable. It counts as a report not retrieved in PRISMA.");
      setOpen(false);
      onMarked(state);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          setOpen(true);
        }}
      >
        <BanIcon aria-hidden="true" /> Not retrievable
      </Button>
    );
  }
  return (
    <form
      className="grid w-full gap-2 rounded-lg border border-border p-3"
      onSubmit={(event) => {
        event.preventDefault();
        mark.mutate();
      }}
    >
      <label htmlFor={id} className="text-sm font-medium">
        Why could the full text not be found?{" "}
        <span className="font-normal text-muted-foreground">(optional)</span>
      </label>
      <Textarea
        id={id}
        rows={2}
        value={note}
        placeholder="e.g. Not held by the library; authors did not reply"
        onChange={(event) => {
          setNote(event.target.value);
        }}
      />
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setOpen(false);
          }}
        >
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={mark.isPending}>
          Mark not retrievable
        </Button>
      </div>
    </form>
  );
}

function NotRetrievableNotice({
  pid,
  rid,
  note,
  canScreen,
  onUndone,
}: {
  pid: string;
  rid: string;
  note: string | null;
  canScreen: boolean;
  onUndone: (state: RecordFulltext) => void;
}) {
  const undo = useMutation({
    mutationFn: () => unmarkNotRetrievable(pid, rid),
    onSuccess: onUndone,
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <div className="grid gap-2 rounded-lg border border-border bg-muted/50 p-4 text-sm">
      <p className="font-semibold">Full text not retrievable</p>
      {note && <p className="whitespace-pre-line">{note}</p>}
      <p className="text-muted-foreground">
        This record is counted in PRISMA as a report not retrieved, and is not screened.
      </p>
      {canScreen && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="justify-self-start"
          disabled={undo.isPending}
          onClick={() => {
            undo.mutate();
          }}
        >
          <Undo2Icon aria-hidden="true" /> It was found after all
        </Button>
      )}
    </div>
  );
}

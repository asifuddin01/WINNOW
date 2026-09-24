import {
  ChevronDownIcon,
  ChevronUpIcon,
  HighlighterIcon,
  Maximize2Icon,
  MinusIcon,
  PlusIcon,
  SearchIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { PDFDocumentLoadingTask } from "pdfjs-dist";
import type { EventBus, PDFViewer } from "pdfjs-dist/web/pdf_viewer.mjs";

import type { Annotation, AnnotationColor } from "@/api/fulltext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ANNOTATION_COLORS, ANNOTATION_FILL, ANNOTATION_NAMES } from "@/features/fulltext/colors";
import { keywordBoxes, toBoxes, type Box } from "@/features/fulltext/geometry";
import { loadPdfjs } from "@/features/fulltext/pdfjs";
import { COLOR_DOT } from "@/features/projects/palette";
import type { Matcher } from "@/features/screening/highlight";
import { cn } from "@/lib/utils";

export interface NewHighlight {
  page: number;
  rects: Box[];
  quote: string;
  color: AnnotationColor;
}

export interface PdfViewerProps {
  data: Uint8Array;
  /** What the PDF is, for screen readers. */
  label: string;
  matchers: Matcher[];
  annotations: Annotation[];
  canAnnotate: boolean;
  onHighlight: (highlight: NewHighlight) => void;
  /** Scroll to a page, e.g. to an annotation chosen in the list; `key` repeats a jump. */
  jump?: { page: number; key: number } | null;
  /** Extra buttons for the toolbar (highlights list, download). */
  actions?: React.ReactNode;
}

/** The part of pdf.js's (untyped) page view the overlay needs. */
interface PageView {
  div: HTMLDivElement;
}

interface Pending {
  page: number;
  rects: Box[];
  quote: string;
}

interface FindState {
  current: number;
  total: number;
  searched: boolean;
}

const MAX_QUOTE = 5_000;
// The server's colour name, which may be one this version does not know.
const FILLS: Partial<Record<string, string>> = ANNOTATION_FILL;
// iOS Safari refuses canvases over 16.7 million pixels; stay under it everywhere.
const MAX_CANVAS_PIXELS = 4096 * 4096;

/**
 * The PDF viewer (guide 8.8): pdf.js's own viewer, with its text layer for selecting and
 * searching, the review's keywords highlighted, and highlight annotations drawn over the
 * page. Highlights and keywords live in an overlay of their own and are positioned as
 * fractions of the page, so zooming never moves them.
 */
export default function PdfViewer({
  data,
  label,
  matchers,
  annotations,
  canAnnotate,
  onHighlight,
  jump,
  actions,
}: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<PDFViewer | null>(null);
  const busRef = useRef<EventBus | null>(null);
  const fitWidth = useRef(true);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [scale, setScale] = useState(1);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<FindState>({ current: 0, total: 0, searched: false });
  const [pending, setPending] = useState<Pending | null>(null);
  const searchId = useId();

  // What the overlay draws; read through a ref so pdf.js's events always see the latest.
  const drawn = useRef({ matchers, annotations });

  const paint = useCallback((pageNumber: number) => {
    const view = viewerRef.current?.getPageView(pageNumber - 1) as PageView | undefined;
    const div = view?.div;
    if (!div) return;
    let overlay = div.querySelector<HTMLDivElement>(":scope > .winnow-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "winnow-overlay";
      overlay.setAttribute("aria-hidden", "true");
      const textLayer = div.querySelector(":scope > .textLayer");
      div.insertBefore(overlay, textLayer);
    }
    overlay.replaceChildren();
    const box = div.getBoundingClientRect();
    const textLayer = div.querySelector<HTMLElement>(":scope > .textLayer");
    if (textLayer) {
      for (const mark of keywordBoxes(textLayer, box, drawn.current.matchers)) {
        overlay.append(piece(mark.box, cn("winnow-keyword", COLOR_DOT[mark.color]), mark.name));
      }
    }
    for (const annotation of drawn.current.annotations) {
      if (annotation.page !== pageNumber) continue;
      const fill = FILLS[annotation.color] ?? ANNOTATION_FILL.yellow;
      for (const rect of annotation.rects) {
        const mark = piece(
          rect as Box,
          cn("winnow-annotation", fill),
          annotation.comment ?? annotation.quote ?? "",
        );
        mark.dataset.annotation = annotation.id;
        overlay.append(mark);
      }
    }
  }, []);

  const repaint = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    for (let index = 0; index < viewer.pagesCount; index++) {
      const view = viewer.getPageView(index) as PageView | undefined;
      if (view?.div.querySelector(":scope > .textLayer")) {
        paint(index + 1);
      }
    }
  }, [paint]);

  // Load the document into a fresh viewer whenever the bytes change.
  useEffect(() => {
    const container = containerRef.current;
    const inner = innerRef.current;
    if (!container || !inner) return;
    // Asked through a function, so the checks after each await are not read as settled.
    let cancelled = false;
    const stopped = () => cancelled;
    let task: PDFDocumentLoadingTask | null = null;
    let resize: ResizeObserver | null = null;

    void (async () => {
      try {
        const { pdfjs, lib } = await loadPdfjs();
        if (stopped()) return;
        const eventBus = new lib.EventBus();
        const linkService = new lib.PDFLinkService({
          eventBus,
          externalLinkTarget: lib.LinkTarget.BLANK,
          externalLinkRel: "noopener noreferrer nofollow",
        });
        const findController = new lib.PDFFindController({ eventBus, linkService });
        const viewer = new lib.PDFViewer({
          container,
          viewer: inner,
          eventBus,
          linkService,
          findController,
          removePageBorders: true,
          // Links work; forms and PDF JavaScript never do.
          annotationMode: pdfjs.AnnotationMode.ENABLE,
          maxCanvasPixels: MAX_CANVAS_PIXELS,
        });
        linkService.setViewer(viewer);
        viewerRef.current = viewer;
        busRef.current = eventBus;

        eventBus.on("pagesinit", () => {
          viewer.currentScaleValue = "page-width";
        });
        eventBus.on("pagechanging", ({ pageNumber }: { pageNumber: number }) => {
          setPage(pageNumber);
        });
        eventBus.on("scalechanging", ({ scale: next }: { scale: number }) => {
          setScale(next);
        });
        eventBus.on("textlayerrendered", ({ pageNumber }: { pageNumber: number }) => {
          paint(pageNumber);
        });
        eventBus.on(
          "updatefindmatchescount",
          ({ matchesCount }: { matchesCount: { current: number; total: number } }) => {
            setFound({ ...matchesCount, searched: true });
          },
        );
        eventBus.on(
          "updatefindcontrolstate",
          ({ matchesCount }: { matchesCount: { current: number; total: number } }) => {
            setFound({ ...matchesCount, searched: true });
          },
        );

        // A copy: pdf.js takes ownership of the buffer it is given.
        task = pdfjs.getDocument({ data: data.slice(), useWasm: false, enableXfa: false });
        const doc = await task.promise;
        if (stopped()) return;
        viewer.setDocument(doc);
        linkService.setDocument(doc);
        setPages(doc.numPages);
        setReady(true);

        // Turning a phone, or opening a side panel, keeps the page fitted to the width.
        resize = new ResizeObserver(() => {
          if (fitWidth.current && viewer.pagesCount > 0) viewer.currentScaleValue = "page-width";
        });
        resize.observe(container);
      } catch {
        if (!stopped()) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      resize?.disconnect();
      viewerRef.current?.cleanup();
      viewerRef.current = null;
      busRef.current = null;
      void task?.destroy();
      setReady(false);
      setPending(null);
    };
  }, [data, paint]);

  useEffect(() => {
    drawn.current = { matchers, annotations };
    repaint();
  }, [matchers, annotations, repaint]);

  useEffect(() => {
    if (!jump || !viewerRef.current) return;
    viewerRef.current.scrollPageIntoView({ pageNumber: jump.page });
  }, [jump]);

  // A selection in the text layer offers to become a highlight.
  useEffect(() => {
    if (!canAnnotate) return;
    const onSelection = () => {
      const selection = document.getSelection();
      const container = containerRef.current;
      if (!selection || selection.isCollapsed || !container) return;
      const anchor = selection.anchorNode;
      if (!anchor || !container.contains(anchor)) return;
      const element = anchor instanceof Element ? anchor : anchor.parentElement;
      const pageDiv = element?.closest<HTMLElement>(".page");
      const pageNumber = Number(pageDiv?.dataset.pageNumber);
      if (!pageDiv || !pageNumber) return;
      const range = selection.getRangeAt(0);
      const rects = toBoxes(Array.from(range.getClientRects()), pageDiv.getBoundingClientRect());
      const quote = selection.toString().replace(/\s+/g, " ").trim().slice(0, MAX_QUOTE);
      if (rects.length === 0 || !quote) return;
      setPending({ page: pageNumber, rects: rects.slice(0, 200), quote });
    };
    document.addEventListener("selectionchange", onSelection);
    return () => {
      document.removeEventListener("selectionchange", onSelection);
    };
  }, [canAnnotate]);

  const find = (again: boolean, previous = false) => {
    busRef.current?.dispatch("find", {
      source: null,
      type: again ? "again" : "",
      query,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: previous,
      matchDiacritics: false,
    });
  };

  const zoom = (how: "in" | "out" | "fit") => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    fitWidth.current = how === "fit";
    if (how === "fit") viewer.currentScaleValue = "page-width";
    else if (how === "in") viewer.increaseScale();
    else viewer.decreaseScale();
  };

  const goTo = (pageNumber: number) => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.currentPageNumber = Math.min(Math.max(pageNumber, 1), viewer.pagesCount);
  };

  const keep = (color: AnnotationColor) => {
    if (!pending) return;
    onHighlight({ ...pending, color });
    setPending(null);
    document.getSelection()?.removeAllRanges();
  };

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <form
          role="search"
          className="flex min-w-0 flex-1 basis-56 items-center gap-1"
          onSubmit={(event) => {
            event.preventDefault();
            find(found.searched && query.length > 0);
          }}
        >
          <label htmlFor={searchId} className="sr-only">
            Search in the PDF
          </label>
          <div className="relative min-w-0 flex-1">
            <SearchIcon
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              id={searchId}
              type="search"
              value={query}
              placeholder="Search in the PDF"
              className="h-8 pl-8"
              disabled={!ready}
              onChange={(event) => {
                setQuery(event.target.value);
                setFound({ current: 0, total: 0, searched: false });
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && event.shiftKey) {
                  event.preventDefault();
                  find(true, true);
                }
              }}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Previous match"
            disabled={!ready || !query}
            onClick={() => {
              find(found.searched, true);
            }}
          >
            <ChevronUpIcon aria-hidden="true" />
          </Button>
          <Button
            type="submit"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Next match"
            disabled={!ready || !query}
          >
            <ChevronDownIcon aria-hidden="true" />
          </Button>
          <span className="w-16 text-xs text-muted-foreground tabular-nums" aria-live="polite">
            {found.searched && query
              ? found.total > 0
                ? `${found.current} of ${found.total}`
                : "No matches"
              : ""}
          </span>
        </form>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Zoom out"
            disabled={!ready}
            onClick={() => {
              zoom("out");
            }}
          >
            <MinusIcon aria-hidden="true" />
          </Button>
          <span className="w-11 text-center text-xs tabular-nums" aria-live="off">
            {Math.round(scale * 100)}%
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Zoom in"
            disabled={!ready}
            onClick={() => {
              zoom("in");
            }}
          >
            <PlusIcon aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Fit to width"
            disabled={!ready}
            onClick={() => {
              zoom("fit");
            }}
          >
            <Maximize2Icon aria-hidden="true" />
          </Button>
          {actions}
        </div>
      </div>

      <div className="relative h-[70dvh] min-h-80 overflow-hidden rounded-lg border border-border bg-muted md:h-[calc(100dvh-13rem)]">
        {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- a scrollable region has to be
            keyboard reachable (axe scrollable-region-focusable), which this rule forbids. */}
        <div
          ref={containerRef}
          // pdf.js requires an absolutely positioned, scrolling container.
          className="winnow-pdf absolute inset-0 overflow-auto"
          tabIndex={0}
          role="document"
          aria-label={`${label}, page ${page} of ${pages || "…"}`}
        >
          <div ref={innerRef} className="pdfViewer" />
        </div>
        {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
        {!ready && !failed && (
          <p className="absolute inset-0 grid place-items-center text-sm text-muted-foreground">
            Opening the PDF…
          </p>
        )}
        {failed && (
          <p
            role="alert"
            className="absolute inset-0 grid place-items-center p-6 text-center text-sm"
          >
            This PDF could not be shown. Download it to open it in another reader.
          </p>
        )}
        {pending && (
          <div
            className="absolute inset-x-2 bottom-2 z-10 mx-auto flex max-w-md flex-wrap items-center justify-center gap-1 rounded-lg border border-border bg-popover p-1.5 shadow-lg"
            role="toolbar"
            aria-label="Highlight the selected text"
          >
            <HighlighterIcon className="mx-1 size-4 text-muted-foreground" aria-hidden="true" />
            {ANNOTATION_COLORS.map((color) => (
              <Button
                key={color}
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5 px-2"
                // Keep the selection while the button is pressed.
                onPointerDown={(event) => {
                  event.preventDefault();
                }}
                onClick={() => {
                  keep(color);
                }}
              >
                <span
                  className={cn(
                    "size-3 rounded-full border border-black/20",
                    ANNOTATION_FILL[color],
                  )}
                  aria-hidden="true"
                />
                {ANNOTATION_NAMES[color]}
              </Button>
            ))}
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-8"
              aria-label="Do not highlight"
              onClick={() => {
                setPending(null);
              }}
            >
              <XIcon aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>

      <div className="flex items-center justify-center gap-2 text-sm">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={!ready || page <= 1}
          onClick={() => {
            goTo(page - 1);
          }}
        >
          <ChevronUpIcon aria-hidden="true" /> Previous page
        </Button>
        <span className="tabular-nums" aria-live="polite">
          Page {page} of {pages || "…"}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={!ready || page >= pages}
          onClick={() => {
            goTo(page + 1);
          }}
        >
          Next page <ChevronDownIcon aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function piece(box: Box, className: string, title: string) {
  const div = document.createElement("div");
  div.className = className;
  div.style.left = `${box[0] * 100}%`;
  div.style.top = `${box[1] * 100}%`;
  div.style.width = `${box[2] * 100}%`;
  div.style.height = `${box[3] * 100}%`;
  if (title) div.title = title;
  return div;
}

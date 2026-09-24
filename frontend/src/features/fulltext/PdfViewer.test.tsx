import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { Annotation } from "@/api/fulltext";
import PdfViewer, { type PdfViewerProps } from "@/features/fulltext/PdfViewer";
import type { Matcher } from "@/features/screening/highlight";

/**
 * pdf.js cannot render in jsdom (no canvas), so its viewer is replaced by a small fake that
 * behaves the same way from the outside: pages appear as `.page` divs with a text layer,
 * and events arrive on the event bus. The real one is exercised by Playwright.
 */
type Listener = (payload: Record<string, unknown>) => void;

class FakeBus {
  listeners = new Map<string, Listener[]>();
  dispatched: [string, Record<string, unknown>][] = [];
  on(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }
  dispatch(name: string, payload: Record<string, unknown>) {
    this.dispatched.push([name, payload]);
    for (const listener of this.listeners.get(name) ?? []) listener(payload);
  }
}

const PAGES = [
  ["Kidney stones on low-dose CT", "Methods: 120 patients"],
  ["Results: sensitivity 0.94 for kidney stones"],
];

class FakeViewer {
  static last: FakeViewer | null = null;
  bus: FakeBus;
  inner: HTMLDivElement;
  scale = 1;
  page = 1;
  scrolledTo: number[] = [];
  views: { div: HTMLDivElement }[] = [];
  cleaned = false;
  constructor(options: { container: HTMLDivElement; viewer: HTMLDivElement; eventBus: FakeBus }) {
    this.bus = options.eventBus;
    this.inner = options.viewer;
    FakeViewer.last = this;
  }
  get pagesCount() {
    return this.views.length;
  }
  getPageView(index: number) {
    return this.views[index];
  }
  setDocument() {
    PAGES.forEach((lines, index) => {
      const div = document.createElement("div");
      div.className = "page";
      div.dataset.pageNumber = String(index + 1);
      div.getBoundingClientRect = () => new DOMRect(0, index * 800, 600, 800);
      const layer = document.createElement("div");
      layer.className = "textLayer";
      for (const line of lines) {
        const span = document.createElement("span");
        span.textContent = line;
        layer.append(span);
      }
      div.append(layer);
      this.inner.append(div);
      this.views.push({ div });
    });
    this.bus.dispatch("pagesinit", {});
    PAGES.forEach((_, index) => {
      this.bus.dispatch("textlayerrendered", { pageNumber: index + 1 });
    });
  }
  set currentScaleValue(value: string) {
    this.scale = value === "page-width" ? 0.9 : Number(value);
    this.bus.dispatch("scalechanging", { scale: this.scale });
  }
  increaseScale() {
    this.scale += 0.1;
    this.bus.dispatch("scalechanging", { scale: this.scale });
  }
  decreaseScale() {
    this.scale -= 0.1;
    this.bus.dispatch("scalechanging", { scale: this.scale });
  }
  set currentPageNumber(value: number) {
    this.page = value;
    this.bus.dispatch("pagechanging", { pageNumber: value });
  }
  scrollPageIntoView({ pageNumber }: { pageNumber: number }) {
    this.scrolledTo.push(pageNumber);
  }
  cleanup() {
    this.cleaned = true;
  }
}

class FakeFind {
  readonly bus: FakeBus;
  constructor({ eventBus }: { eventBus: FakeBus }) {
    this.bus = eventBus;
    eventBus.on("find", (state) => {
      const found = state.type === "again" ? (state.findPrevious ? 1 : 2) : 1;
      eventBus.dispatch("updatefindmatchescount", { matchesCount: { current: found, total: 3 } });
      eventBus.dispatch("updatefindcontrolstate", { matchesCount: { current: found, total: 3 } });
    });
  }
}

let failing = false;
const destroyed = vi.fn();

vi.mock("@/features/fulltext/pdfjs", () => ({
  loadPdfjs: () =>
    Promise.resolve({
      pdfjs: {
        AnnotationMode: { ENABLE: 1 },
        getDocument: () => ({
          promise: failing
            ? Promise.reject(new Error("bad PDF"))
            : Promise.resolve({ numPages: 2 }),
          destroy: destroyed,
        }),
      },
      lib: {
        EventBus: FakeBus,
        LinkTarget: { BLANK: 2 },
        PDFLinkService: class {
          viewer: unknown = null;
          document: unknown = null;
          setViewer(viewer: unknown) {
            this.viewer = viewer;
          }
          setDocument(document: unknown) {
            this.document = document;
          }
        },
        PDFFindController: FakeFind,
        PDFViewer: FakeViewer,
      },
    }),
}));

const KIDNEY: Matcher = {
  groupId: "g1",
  name: "Kidney",
  color: "teal",
  pattern: /kidney/giu,
};

const HIGHLIGHT: Annotation = {
  id: "a1",
  page: 2,
  rects: [[0.1, 0.2, 0.5, 0.02]],
  color: "pink",
  quote: "sensitivity 0.94",
  comment: "Accuracy outcome",
  author: "Ada",
  mine: true,
  created_at: "2026-09-24T10:00:00Z",
};

// One array for the whole file: new bytes reload the document, as they should.
const BYTES = new Uint8Array([37, 80, 68, 70]);

function viewer(props: Partial<PdfViewerProps> = {}) {
  const onHighlight = vi.fn();
  const view = render(
    <PdfViewer
      data={BYTES}
      label="Kidney stones on CT"
      matchers={[KIDNEY]}
      annotations={[HIGHLIGHT]}
      canAnnotate
      onHighlight={onHighlight}
      {...props}
    />,
  );
  return { ...view, onHighlight };
}

beforeEach(() => {
  failing = false;
  FakeViewer.last = null;
  // jsdom lays nothing out; give selected and matched text a size on its page.
  Range.prototype.getClientRects = () => [new DOMRect(60, 100, 120, 16)] as unknown as DOMRectList;
});

afterEach(() => {
  document.getSelection()?.removeAllRanges();
});

describe("the PDF viewer", () => {
  test("opens the document fitted to the width and says which page is shown", async () => {
    viewer();
    const doc = await screen.findByRole("document", { name: "Kidney stones on CT, page 1 of 2" });
    expect(doc).toBeVisible();
    expect(screen.getByText("90%")).toBeVisible();
    expect(screen.getByText("Page 1 of 2")).toBeVisible();
  });

  test("draws the review's keywords and the highlights over the pages", async () => {
    const { container } = viewer();
    await screen.findByText("Page 1 of 2");
    const keywords = container.querySelectorAll(".winnow-keyword");
    // "Kidney" on page 1 and "kidney" on page 2.
    expect(keywords).toHaveLength(2);
    expect(keywords[0]).toHaveAttribute("title", "Kidney");
    expect((keywords[0] as HTMLElement).style.left).toBe("10%");
    const [mark] = container.querySelectorAll<HTMLElement>(".winnow-annotation");
    expect(mark?.dataset.annotation).toBe("a1");
    expect(mark?.closest(".page")).toHaveAttribute("data-page-number", "2");
    expect(mark?.style.width).toBe("50%");
    expect(mark).toHaveAttribute("title", "Accuracy outcome");
  });

  test("redraws when the highlights change, and follows a jump", async () => {
    const { container, rerender, onHighlight } = viewer();
    await screen.findByText("Page 1 of 2");
    rerender(
      <PdfViewer
        data={BYTES}
        label="Kidney stones on CT"
        matchers={[]}
        annotations={[]}
        canAnnotate
        onHighlight={onHighlight}
        jump={{ page: 2, key: 1 }}
      />,
    );
    await waitFor(() => {
      expect(container.querySelectorAll(".winnow-annotation, .winnow-keyword")).toHaveLength(0);
    });
    expect(FakeViewer.last?.scrolledTo).toEqual([2]);
  });

  test("searches inside the PDF, forwards and back", async () => {
    const user = userEvent.setup();
    viewer();
    await screen.findByText("Page 1 of 2");
    const search = screen.getByRole("searchbox", { name: "Search in the PDF" });
    await user.type(search, "kidney{Enter}");
    expect(await screen.findByText("1 of 3")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next match" }));
    expect(await screen.findByText("2 of 3")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Previous match" }));
    expect(await screen.findByText("1 of 3")).toBeVisible();
    await user.type(search, "{Shift>}{Enter}{/Shift}");
    const finds = FakeViewer.last?.bus.dispatched.filter(([name]) => name === "find") ?? [];
    expect(finds.map(([, state]) => [state.type, state.findPrevious])).toEqual([
      ["", false],
      ["again", false],
      ["again", true],
      ["again", true],
    ]);
    expect(finds[0]?.[1]).toMatchObject({ query: "kidney", highlightAll: true });
  });

  test("zooms, fits to the width again, and turns pages", async () => {
    const user = userEvent.setup();
    viewer();
    await screen.findByText("Page 1 of 2");
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByText("100%")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(screen.getByText("80%")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Fit to width" }));
    expect(screen.getByText("90%")).toBeVisible();

    expect(screen.getByRole("button", { name: /Previous page/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Next page/ }));
    expect(screen.getByText("Page 2 of 2")).toBeVisible();
    expect(screen.getByRole("button", { name: /Next page/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Previous page/ }));
    expect(screen.getByText("Page 1 of 2")).toBeVisible();
  });

  test("a selection in the text becomes a highlight in the colour chosen", async () => {
    const user = userEvent.setup();
    const { container, onHighlight } = viewer();
    await screen.findByText("Page 1 of 2");
    const span = container.querySelector<HTMLElement>('.page[data-page-number="2"] span');
    const text = span?.firstChild;
    if (!text) throw new Error("no text on page 2");
    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 16);
    act(() => {
      document.getSelection()?.addRange(range);
      document.dispatchEvent(new Event("selectionchange"));
    });

    const toolbar = await screen.findByRole("toolbar", { name: "Highlight the selected text" });
    await user.click(within(toolbar).getByRole("button", { name: "Green" }));
    expect(onHighlight).toHaveBeenCalledWith({
      page: 2,
      // The selection's box (60, 100, 120 × 16) on page 2's (0, 800, 600 × 800): above
      // the page's top, so kept on the page.
      rects: [[0.1, 0, 0.2, 0.02]],
      quote: "Results: sensiti",
      color: "green",
    });
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  test("a selection can be let go without highlighting; viewers cannot highlight", async () => {
    const user = userEvent.setup();
    const { container } = viewer();
    await screen.findByText("Page 1 of 2");
    const text = container.querySelector(".page span")?.firstChild;
    if (!text) throw new Error("no text");
    const range = document.createRange();
    range.selectNodeContents(text);
    act(() => {
      document.getSelection()?.addRange(range);
      document.dispatchEvent(new Event("selectionchange"));
    });
    await user.click(await screen.findByRole("button", { name: "Do not highlight" }));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  test("a PDF pdf.js cannot read says so and offers the download", async () => {
    failing = true;
    viewer();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This PDF could not be shown. Download it",
    );
  });

  test("closing the viewer lets pdf.js go", async () => {
    const { unmount } = viewer({ canAnnotate: false });
    await screen.findByText("Page 1 of 2");
    const shown = FakeViewer.last;
    unmount();
    expect(shown?.cleaned).toBe(true);
    expect(destroyed).toHaveBeenCalled();
  });
});

/**
 * pdf.js, loaded only when a PDF is opened (guide 11.1: the viewer is its own chunk).
 *
 * The worker is served from our own origin (CSP `worker-src 'self'`). WebAssembly stays
 * off, since the CSP does not allow it; pdf.js then decodes the rare JPEG 2000 and JBIG2
 * images more slowly, or not at all. PDF JavaScript never runs: no scripting manager.
 */
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export type PdfJs = typeof import("pdfjs-dist");
export type PdfViewerLib = typeof import("pdfjs-dist/web/pdf_viewer.mjs");

let loading: Promise<{ pdfjs: PdfJs; lib: PdfViewerLib }> | null = null;

export function loadPdfjs() {
  loading ??= (async () => {
    const pdfjs = await import("pdfjs-dist");
    pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
    // The viewer components read the library from here when their module is evaluated.
    (globalThis as { pdfjsLib?: PdfJs }).pdfjsLib = pdfjs;
    const lib = await import("pdfjs-dist/web/pdf_viewer.mjs");
    await import("pdfjs-dist/web/pdf_viewer.css");
    return { pdfjs, lib };
  })();
  return loading;
}

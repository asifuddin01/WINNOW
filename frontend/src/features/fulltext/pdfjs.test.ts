import { expect, test, vi } from "vitest";

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "/assets/pdf.worker.mjs" }));
vi.mock("pdfjs-dist", () => ({ GlobalWorkerOptions: { workerSrc: "" }, version: "test" }));
vi.mock("pdfjs-dist/web/pdf_viewer.mjs", () => ({
  // The viewer module reads the library from the global when it is evaluated.
  seenLibrary: (globalThis as { pdfjsLib?: { version: string } }).pdfjsLib?.version,
}));
vi.mock("pdfjs-dist/web/pdf_viewer.css", () => ({}));

test("pdf.js loads once, with its worker from our own origin, before its viewer", async () => {
  const { loadPdfjs } = await import("@/features/fulltext/pdfjs");
  const first = loadPdfjs();
  expect(loadPdfjs()).toBe(first);
  const { pdfjs, lib } = await first;
  expect(pdfjs.GlobalWorkerOptions.workerSrc).toBe("/assets/pdf.worker.mjs");
  expect((lib as unknown as { seenLibrary: string }).seenLibrary).toBe("test");
});

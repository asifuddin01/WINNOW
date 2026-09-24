import { queryOptions } from "@tanstack/react-query";

import { ApiError, api, unwrap } from "@/api/client";
import { csrfToken } from "@/api/csrf";
import type { components } from "@/api/schema";

export type FulltextOut = components["schemas"]["FulltextOut"];
export type RecordFulltext = components["schemas"]["RecordFulltext"];
export type FulltextRecord = components["schemas"]["FulltextRecord"];
export type FulltextSummary = components["schemas"]["FulltextSummary"];
export type Annotation = components["schemas"]["AnnotationOut"];
export type AnnotationIn = components["schemas"]["AnnotationIn"];
export type AnnotationColor = NonNullable<AnnotationIn["color"]>;
export type OpenAccessFinds = components["schemas"]["OpenAccessFinds"];
export type Batch = components["schemas"]["BatchOut"];
export type BatchEntry = components["schemas"]["BatchEntryOut"];
export type BatchApplied = components["schemas"]["BatchApplied"];
export type ScanStatus = FulltextOut["scan_status"];

export const fulltextKeys = {
  all: (pid: string) => ["projects", pid, "fulltext"] as const,
  summary: (pid: string) => ["projects", pid, "fulltext", "summary"] as const,
  records: (pid: string) => ["projects", pid, "fulltext", "records"] as const,
  record: (pid: string, rid: string) => ["projects", pid, "fulltext", "record", rid] as const,
  annotations: (pid: string, fid: string) =>
    ["projects", pid, "fulltext", "annotations", fid] as const,
  batch: (pid: string, bid: string) => ["projects", pid, "fulltext", "batch", bid] as const,
};

/** Whether a PDF may be opened: cleared by the scanner, or on an instance without one. */
export const readable = (status: ScanStatus | undefined) =>
  status === "clean" || status === "skipped";

export const fulltextSummaryQuery = (pid: string) =>
  queryOptions({
    queryKey: fulltextKeys.summary(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/fulltext/summary", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const fulltextRecordsQuery = (pid: string) =>
  queryOptions({
    queryKey: fulltextKeys.records(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/fulltext/records", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const recordFulltextQuery = (pid: string, rid: string) =>
  queryOptions({
    queryKey: fulltextKeys.record(pid, rid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records/{rid}/fulltext", {
          signal,
          params: { path: { pid, rid } },
        }),
      ),
    // A PDF being scanned becomes readable within seconds; look again until it has.
    refetchInterval: (query) =>
      query.state.data?.fulltext?.scan_status === "pending" ? 2000 : false,
  });

export const annotationsQuery = (pid: string, fid: string) =>
  queryOptions({
    queryKey: fulltextKeys.annotations(pid, fid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/fulltext/{fid}/annotations", {
          signal,
          params: { path: { pid, fid } },
        }),
      ),
  });

/** The PDF's bytes, held briefly so going back to a record does not fetch it again. */
export const pdfQuery = (pid: string, rid: string, fid: string) =>
  queryOptions({
    queryKey: ["projects", pid, "fulltext", "pdf", fid] as const,
    queryFn: ({ signal }) => fetchPdf(pid, rid, signal),
    staleTime: Infinity,
    gcTime: 60_000,
    retry: 1,
  });

export const batchQuery = (pid: string, bid: string) =>
  queryOptions({
    queryKey: fulltextKeys.batch(pid, bid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/fulltext/bulk/{bid}", {
          signal,
          params: { path: { pid, bid } },
        }),
      ),
    refetchInterval: (query) => (query.state.data?.status === "checking" ? 1500 : false),
  });

/**
 * Files go as form data, which openapi-fetch would serialise wrongly; this is fetch with
 * the CSRF header the client adds (like `uploadImports`).
 */
async function postFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file, file.name);
  const response = await fetch(`${window.location.origin}/api/v1${path}`, {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: { "X-CSRF-Token": await csrfToken(), Accept: "application/json" },
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, payload as never);
  return payload as T;
}

export const uploadPdf = (pid: string, rid: string, file: File) =>
  postFile<FulltextOut>(`/projects/${pid}/records/${rid}/fulltext`, file);

export const uploadZip = (pid: string, file: File) =>
  postFile<Batch>(`/projects/${pid}/fulltext/bulk`, file);

/** The PDF's bytes, through a link that lasts five minutes and works only for me. */
export async function fetchPdf(pid: string, rid: string, signal?: AbortSignal) {
  const link = unwrap(
    await api.GET("/api/v1/projects/{pid}/records/{rid}/fulltext/url", {
      signal,
      params: { path: { pid, rid } },
    }),
  );
  const response = await fetch(`${window.location.origin}${link.url}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, null);
  return new Uint8Array(await response.arrayBuffer());
}

/** A download: the browser follows a short-lived link that answers as an attachment. */
export async function downloadLink(pid: string, rid: string) {
  const link = unwrap(
    await api.GET("/api/v1/projects/{pid}/records/{rid}/fulltext/url", {
      params: { path: { pid, rid }, query: { download: true } },
    }),
  );
  return `${window.location.origin}${link.url}`;
}

export async function findOpenAccess(pid: string, rid: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/records/{rid}/fulltext/find-oa", {
      params: { path: { pid, rid } },
    }),
  );
}

export async function fetchOpenAccess(pid: string, rid: string, candidate: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/records/{rid}/fulltext/fetch-oa", {
      params: { path: { pid, rid } },
      body: { candidate },
    }),
  );
}

export async function markNotRetrievable(pid: string, rid: string, note: string | null) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/records/{rid}/fulltext/not-retrievable", {
      params: { path: { pid, rid } },
      body: { note },
    }),
  );
}

export async function unmarkNotRetrievable(pid: string, rid: string) {
  return unwrap(
    await api.DELETE("/api/v1/projects/{pid}/records/{rid}/fulltext/not-retrievable", {
      params: { path: { pid, rid } },
    }),
  );
}

export async function addAnnotation(pid: string, fid: string, body: AnnotationIn) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/fulltext/{fid}/annotations", {
      params: { path: { pid, fid } },
      body,
    }),
  );
}

export async function updateAnnotation(
  pid: string,
  fid: string,
  aid: string,
  body: { comment?: string | null; color?: AnnotationColor | null },
) {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/fulltext/{fid}/annotations/{aid}", {
      params: { path: { pid, fid, aid } },
      body,
    }),
  );
}

export async function deleteAnnotation(pid: string, fid: string, aid: string) {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/fulltext/{fid}/annotations/{aid}", {
      params: { path: { pid, fid, aid } },
    }),
  );
}

export async function confirmBatch(
  pid: string,
  bid: string,
  choices: Record<string, string>,
  replace: boolean,
) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/fulltext/bulk/{bid}/confirm", {
      params: { path: { pid, bid } },
      body: { choices, replace },
    }),
  );
}

export async function discardBatch(pid: string, bid: string) {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/fulltext/bulk/{bid}", {
      params: { path: { pid, bid } },
    }),
  );
}

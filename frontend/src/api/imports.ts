import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { csrfToken } from "@/api/csrf";
import type { components } from "@/api/schema";

export type ImportBatch = components["schemas"]["ImportOut"];
export type ImportPreview = components["schemas"]["ImportPreview"];
export type ImportProblem = components["schemas"]["ImportProblem"];
export type ConfirmImport = components["schemas"]["ConfirmImport"];

export const importKeys = {
  list: (pid: string) => ["projects", pid, "imports"] as const,
  preview: (pid: string, bid: string) => ["projects", pid, "imports", bid, "preview"] as const,
};

export const importsQuery = (pid: string) =>
  queryOptions({
    queryKey: importKeys.list(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/imports", { signal, params: { path: { pid } } }),
      ),
  });

export const importPreviewQuery = (pid: string, bid: string) =>
  queryOptions({
    queryKey: importKeys.preview(pid, bid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/imports/{bid}/preview", {
          signal,
          params: { path: { pid, bid } },
        }),
      ),
    retry: false,
  });

export interface UploadFields {
  file: File;
  database_name: string;
  source_name?: string;
  search_date?: string;
  search_string?: string;
}

/**
 * Uploading is the one call that is not JSON: the file goes as form data, and openapi-fetch
 * would serialise it wrongly, so this uses fetch with the same CSRF header the client adds.
 */
export async function uploadImport(pid: string, fields: UploadFields): Promise<ImportBatch> {
  const body = new FormData();
  body.append("file", fields.file, fields.file.name);
  body.append("database_name", fields.database_name);
  if (fields.source_name) body.append("source_name", fields.source_name);
  if (fields.search_date) body.append("search_date", fields.search_date);
  if (fields.search_string) body.append("search_string", fields.search_string);
  // Absolute, like the generated client: a relative URL has no origin to resolve against
  // outside a browser window.
  const response = await fetch(`${window.location.origin}/api/v1/projects/${pid}/imports`, {
    method: "POST",
    body,
    credentials: "same-origin",
    headers: { "X-CSRF-Token": await csrfToken(), Accept: "application/json" },
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const { ApiError } = await import("@/api/client");
    throw new ApiError(response.status, payload as never);
  }
  return payload as ImportBatch;
}

export async function confirmImport(
  pid: string,
  bid: string,
  body: ConfirmImport,
): Promise<ImportBatch> {
  const accepted = unwrap(
    await api.POST("/api/v1/projects/{pid}/imports/{bid}/confirm", {
      params: { path: { pid, bid } },
      body,
    }),
  );
  return accepted.batch;
}

export async function undoImport(pid: string, bid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/imports/{bid}", { params: { path: { pid, bid } } }),
  );
}

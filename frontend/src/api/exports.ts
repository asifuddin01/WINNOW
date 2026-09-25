import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { postFile } from "@/api/fulltext";
import type { components } from "@/api/schema";

export type ExportJob = components["schemas"]["ExportOut"];
export type ExportIn = components["schemas"]["ExportIn"];
export type ExportFormat = ExportJob["format"];
export type RecordFilters = components["schemas"]["RecordFiltersIn"];
export type RestoreJob = components["schemas"]["RestoreOut"];

/** Still being made: look again until it is ready or has failed. */
export const working = (status: ExportJob["status"] | undefined) =>
  status === "queued" || status === "running";

export const exportKeys = {
  all: (pid: string) => ["projects", pid, "exports"] as const,
  restore: (id: string) => ["restores", id] as const,
};

export const exportsQuery = (pid: string) =>
  queryOptions({
    queryKey: exportKeys.all(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/exports", { signal, params: { path: { pid } } }),
      ),
    refetchInterval: (query) =>
      query.state.data?.some((job) => working(job.status)) ? 1500 : false,
  });

export async function requestExport(pid: string, body: ExportIn) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/exports", { params: { path: { pid } }, body }),
  );
}

export function exportFileUrl(pid: string, eid: string): string {
  return `/api/v1/projects/${pid}/exports/${eid}/file`;
}

/** Upload a backup ZIP; the review is built in the worker. */
export const startRestore = (file: File) => postFile<RestoreJob>("/restores", file);

export const restoreQuery = (id: string) =>
  queryOptions({
    queryKey: exportKeys.restore(id),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/restores/{restore_id}", {
          signal,
          params: { path: { restore_id: id } },
        }),
      ),
    refetchInterval: (query) => (working(query.state.data?.status) ? 1500 : false),
  });

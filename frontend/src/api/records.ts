import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Record = components["schemas"]["RecordOut"];
export type RecordDetail = components["schemas"]["RecordDetail"];
export type RecordPage = components["schemas"]["RecordPage"];
export type RecordFacets = components["schemas"]["RecordFacets"];
export type TitleAbstractStatus = components["schemas"]["TitleAbstractStatus"];
export type FullTextStatus = components["schemas"]["FullTextStatus"];
export type Sort = "added" | "oldest" | "year" | "year_asc" | "title" | "relevance";

export interface RecordQuery {
  q?: string;
  status?: TitleAbstractStatus;
  full_text?: FullTextStatus;
  batch?: string;
  duplicates?: boolean;
  sort?: Sort;
  limit?: number;
}

export const recordKeys = {
  list: (pid: string, query: RecordQuery) => ["projects", pid, "records", query] as const,
  facets: (pid: string) => ["projects", pid, "records", "facets"] as const,
  detail: (pid: string, rid: string) => ["projects", pid, "records", rid] as const,
};

/** The records table, a page at a time, for the virtualised list. */
export const recordsQuery = (pid: string, query: RecordQuery = {}) =>
  infiniteQueryOptions({
    queryKey: recordKeys.list(pid, query),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records", {
          signal,
          params: {
            path: { pid },
            query: { ...query, limit: query.limit ?? 50, cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (page: RecordPage) => page.next_cursor ?? undefined,
  });

export const facetsQuery = (pid: string) =>
  queryOptions({
    queryKey: recordKeys.facets(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records/facets", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const recordQuery = (pid: string, rid: string) =>
  queryOptions({
    queryKey: recordKeys.detail(pid, rid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records/{rid}", {
          signal,
          params: { path: { pid, rid } },
        }),
      ),
  });

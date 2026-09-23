import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Cluster = components["schemas"]["ClusterOut"];
export type ClusterMember = components["schemas"]["ClusterMember"];
export type DedupSummary = components["schemas"]["DedupSummary"];
export type ClusterStatus = components["schemas"]["ClusterStatus"];

export const dedupKeys = {
  all: (pid: string) => ["projects", pid, "dedup"] as const,
  summary: (pid: string) => ["projects", pid, "dedup", "summary"] as const,
  clusters: (pid: string, status: ClusterStatus) =>
    ["projects", pid, "dedup", "clusters", status] as const,
};

export const dedupSummaryQuery = (pid: string) =>
  queryOptions({
    queryKey: dedupKeys.summary(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/dedup/summary", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const clustersQuery = (pid: string, status: ClusterStatus = "pending") =>
  queryOptions({
    queryKey: dedupKeys.clusters(pid, status),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/dedup/clusters", {
          signal,
          params: { path: { pid }, query: { status } },
        }),
      ),
  });

export async function runDedup(pid: string) {
  return unwrap(await api.POST("/api/v1/projects/{pid}/dedup/run", { params: { path: { pid } } }));
}

export async function mergeCluster(pid: string, cid: string, primaryId: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/dedup/clusters/{cid}/merge", {
      params: { path: { pid, cid } },
      body: { primary_id: primaryId },
    }),
  );
}

export async function ignoreCluster(pid: string, cid: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/dedup/clusters/{cid}/ignore", {
      params: { path: { pid, cid } },
    }),
  );
}

export async function autoResolve(pid: string, minScore = 0.98) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/dedup/auto-resolve", {
      params: { path: { pid } },
      body: { min_score: minScore },
    }),
  );
}

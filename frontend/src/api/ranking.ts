import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import type { Stage } from "@/api/screening";

export type RankingStatus = components["schemas"]["RankingStatus"];
export type RecallCurve = components["schemas"]["RecallCurve"];
export type Curve = components["schemas"]["Curve"];
export type StoppingAdvice = components["schemas"]["StoppingAdvice"];

export const rankingKeys = {
  all: (pid: string) => ["projects", pid, "ranking"] as const,
  status: (pid: string, stage: Stage) => ["projects", pid, "ranking", "status", stage] as const,
  curve: (pid: string, stage: Stage) => ["projects", pid, "ranking", "curve", stage] as const,
  // Under "screening", so that it is refreshed with the progress after decisions.
  stopping: (pid: string, stage: Stage) =>
    ["projects", pid, "screening", "stopping", stage] as const,
};

export const rankingStatusQuery = (pid: string, stage: Stage) =>
  queryOptions({
    queryKey: rankingKeys.status(pid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/ranking/status", {
          signal,
          params: { path: { pid }, query: { stage } },
        }),
      ),
  });

export const recallCurveQuery = (pid: string, stage: Stage) =>
  queryOptions({
    queryKey: rankingKeys.curve(pid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/ranking/curve", {
          signal,
          params: { path: { pid }, query: { stage } },
        }),
      ),
  });

export const stoppingQuery = (pid: string, stage: Stage) =>
  queryOptions({
    queryKey: rankingKeys.stopping(pid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/screening/stopping", {
          signal,
          params: { path: { pid }, query: { stage } },
        }),
      ),
  });

export async function trainRanking(pid: string, stage: Stage) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/ranking/train", {
      params: { path: { pid }, query: { stage } },
    }),
  );
}

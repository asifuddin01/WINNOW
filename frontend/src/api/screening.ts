import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type ScreeningItem = components["schemas"]["ScreeningItem"];
export type MyDecision = components["schemas"]["MyDecision"];
export type OtherDecision = components["schemas"]["OtherDecision"];
export type DecisionValue = components["schemas"]["DecisionValue"];
export type Progress = components["schemas"]["Progress"];
export type HistoryItem = components["schemas"]["HistoryItem"];
export type Note = components["schemas"]["NoteOut"];
export type NoteVisibility = components["schemas"]["NoteVisibility"];
export type Stage = components["schemas"]["ScreeningStage"];
export type QueueSort = "relevance" | "random" | "year" | "title" | "added";
export type Conflict = components["schemas"]["ConflictOut"];
export type ConflictPage = components["schemas"]["ConflictPage"];
export type FinalDecision = components["schemas"]["FinalDecision"];
export type BulkDecision = components["schemas"]["BulkDecisionIn"];

export const screeningKeys = {
  all: (pid: string) => ["projects", pid, "screening"] as const,
  progress: (pid: string, stage: Stage) =>
    ["projects", pid, "screening", "progress", stage] as const,
  history: (pid: string, stage: Stage) => ["projects", pid, "screening", "history", stage] as const,
  item: (pid: string, rid: string, stage: Stage) =>
    ["projects", pid, "screening", "item", rid, stage] as const,
  conflicts: (pid: string, stage: Stage, pair: string) =>
    ["projects", pid, "conflicts", stage, pair] as const,
};

export async function fetchQueue(
  pid: string,
  options: { stage: Stage; n: number; sort: QueueSort; exclude: string[]; q: string },
  signal?: AbortSignal,
): Promise<ScreeningItem[]> {
  const page = unwrap(
    await api.GET("/api/v1/projects/{pid}/screening/queue", {
      signal,
      params: {
        path: { pid },
        query: {
          stage: options.stage,
          n: options.n,
          sort: options.sort,
          exclude: options.exclude.length ? options.exclude : undefined,
          q: options.q || undefined,
        },
      },
    }),
  );
  return page.items;
}

export const progressQuery = (pid: string, stage: Stage) =>
  queryOptions({
    queryKey: screeningKeys.progress(pid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/screening/progress", {
          signal,
          params: { path: { pid }, query: { stage } },
        }),
      ),
  });

export const historyQuery = (pid: string, stage: Stage) =>
  queryOptions({
    queryKey: screeningKeys.history(pid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/my-history", {
          signal,
          params: { path: { pid }, query: { stage, limit: 50 } },
        }),
      ),
  });

export async function fetchItem(pid: string, rid: string, stage: Stage): Promise<ScreeningItem> {
  return unwrap(
    await api.GET("/api/v1/projects/{pid}/screening/records/{rid}", {
      params: { path: { pid, rid }, query: { stage } },
    }),
  );
}

export interface DecisionBody {
  stage: Stage;
  decision: DecisionValue;
  reason_ids: string[];
  note?: string | null;
  time_spent_ms: number;
}

export async function putDecision(pid: string, rid: string, body: DecisionBody) {
  return unwrap(
    await api.PUT("/api/v1/projects/{pid}/records/{rid}/decision", {
      params: { path: { pid, rid } },
      body,
    }),
  );
}

export async function deleteDecision(pid: string, rid: string, stage: Stage) {
  return unwrap(
    await api.DELETE("/api/v1/projects/{pid}/records/{rid}/decision", {
      params: { path: { pid, rid }, query: { stage } },
    }),
  );
}

export async function putLabels(pid: string, rid: string, labelIds: string[]) {
  return unwrap(
    await api.PUT("/api/v1/projects/{pid}/records/{rid}/labels", {
      params: { path: { pid, rid } },
      body: { label_ids: labelIds },
    }),
  );
}

export async function postNote(
  pid: string,
  rid: string,
  body: string,
  visibility: NoteVisibility,
): Promise<Note> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/records/{rid}/notes", {
      params: { path: { pid, rid } },
      body: { body, visibility },
    }),
  );
}

export async function removeNote(pid: string, nid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/notes/{nid}", { params: { path: { pid, nid } } }),
  );
}

export const conflictsQuery = (pid: string, stage: Stage, pair: { a?: string; b?: string } = {}) =>
  queryOptions({
    queryKey: screeningKeys.conflicts(pid, stage, `${pair.a ?? ""}:${pair.b ?? ""}`),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/conflicts", {
          signal,
          params: {
            path: { pid },
            query: {
              stage,
              reviewer_a: pair.a && pair.b ? pair.a : undefined,
              reviewer_b: pair.a && pair.b ? pair.b : undefined,
              limit: 50,
            },
          },
        }),
      ),
  });

export async function resolveConflict(
  pid: string,
  rid: string,
  body: { stage: Stage; final_decision: FinalDecision; reason_ids: string[]; note?: string },
) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/conflicts/{rid}/resolve", {
      params: { path: { pid, rid } },
      body,
    }),
  );
}

export async function discussConflict(pid: string, rid: string, body: string, stage: Stage) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/conflicts/{rid}/discuss", {
      params: { path: { pid, rid } },
      body: { body, stage },
    }),
  );
}

export async function previewBulk(pid: string, body: BulkDecision): Promise<number> {
  const result = unwrap(
    await api.POST("/api/v1/projects/{pid}/bulk-decision/preview", {
      params: { path: { pid } },
      body,
    }),
  );
  return result.decided;
}

export async function applyBulk(pid: string, body: BulkDecision): Promise<number> {
  const result = unwrap(
    await api.POST("/api/v1/projects/{pid}/bulk-decision", { params: { path: { pid } }, body }),
  );
  return result.decided;
}

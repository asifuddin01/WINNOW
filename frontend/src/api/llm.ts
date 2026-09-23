import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import type { Stage } from "@/api/screening";

export type Suggestion = components["schemas"]["SuggestionOut"];

export const llmKeys = {
  suggestion: (pid: string, rid: string, stage: Stage) =>
    ["projects", pid, "llm", rid, stage] as const,
};

/** My last suggestion for a record, if I asked for one. Sends nothing to the provider. */
export const suggestionQuery = (pid: string, rid: string, stage: Stage) =>
  queryOptions({
    queryKey: llmKeys.suggestion(pid, rid, stage),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/records/{rid}/llm-suggest", {
          signal,
          params: { path: { pid, rid }, query: { stage } },
        }),
      ).suggestion,
  });

/** Ask the review's AI provider about this record now. */
export async function askSuggestion(pid: string, rid: string, stage: Stage): Promise<Suggestion> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/records/{rid}/llm-suggest", {
      params: { path: { pid, rid }, query: { stage } },
    }),
  );
}

export function suggestionsExportUrl(pid: string): string {
  return `/api/v1/projects/${pid}/llm-suggestions.csv`;
}

import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type RobTool = components["schemas"]["ToolOut"];
export type RobVariant = components["schemas"]["VariantOut"];
export type RobDomain = components["schemas"]["DomainOut"];
export type Assessment = components["schemas"]["AssessmentOut"];
export type AssessmentIn = components["schemas"]["AssessmentIn"];
export type RecordRob = components["schemas"]["RecordRob"];
export type StudyStatus = components["schemas"]["StudyStatus"];
export type RobSummary = components["schemas"]["RobSummary"];

export const robKeys = {
  all: (pid: string) => ["projects", pid, "rob"] as const,
  tools: (pid: string) => ["projects", pid, "rob", "tools"] as const,
  studies: (pid: string, tool: string) => ["projects", pid, "rob", "studies", tool] as const,
  summary: (pid: string, tool: string) => ["projects", pid, "rob", "summary", tool] as const,
  record: (pid: string, rid: string) => ["projects", pid, "rob", "record", rid] as const,
};

export const robToolsQuery = (pid: string) =>
  queryOptions({
    queryKey: robKeys.tools(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/rob/tools", { signal, params: { path: { pid } } }),
      ),
    staleTime: Infinity,
  });

export const robStudiesQuery = (pid: string, tool: string) =>
  queryOptions({
    queryKey: robKeys.studies(pid, tool),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/rob/studies", {
          signal,
          params: { path: { pid }, query: { tool } },
        }),
      ),
  });

export const robSummaryQuery = (pid: string, tool: string) =>
  queryOptions({
    queryKey: robKeys.summary(pid, tool),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/rob/summary", {
          signal,
          params: { path: { pid }, query: { tool } },
        }),
      ),
  });

export const recordRobQuery = (pid: string, rid: string) =>
  queryOptions({
    queryKey: robKeys.record(pid, rid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/rob/{rid}", {
          signal,
          params: { path: { pid, rid } },
        }),
      ),
  });

export async function saveAssessment(pid: string, rid: string, body: AssessmentIn) {
  return unwrap(
    await api.PUT("/api/v1/projects/{pid}/rob/{rid}", { params: { path: { pid, rid } }, body }),
  );
}

export async function deleteAssessment(pid: string, rid: string, tool: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/rob/{rid}", {
      params: { path: { pid, rid }, query: { tool } },
    }),
  );
}

export async function chooseFinal(pid: string, rid: string, assessmentId: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/rob/{rid}/final", {
      params: { path: { pid, rid } },
      body: { assessment_id: assessmentId },
    }),
  );
}

export type RobPlot = "traffic-light" | "summary";

export function robPlotUrl(
  pid: string,
  tool: string,
  {
    plot,
    variant,
    format = "svg",
    inline = false,
  }: {
    plot: RobPlot;
    variant?: string;
    format?: "svg" | "png";
    inline?: boolean;
  },
): string {
  const query = new URLSearchParams({ tool, plot });
  if (variant) query.set("variant", variant);
  if (inline) query.set("inline", "true");
  return `/api/v1/projects/${pid}/rob/summary.${format}?${query.toString()}`;
}

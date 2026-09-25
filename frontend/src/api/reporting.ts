import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Prisma = components["schemas"]["PrismaOut"];
export type PrismaManualIn = components["schemas"]["PrismaManualIn"];
export type Stats = components["schemas"]["StatsOut"];
export type StageStats = components["schemas"]["StageStats"];
export type Agreement = components["schemas"]["Agreement"];
export type AuditEntry = components["schemas"]["AuditEntryOut"];
export type Methods = components["schemas"]["MethodsOut"];

export interface AuditFilters {
  action?: string;
  user_id?: string;
  since?: string;
  until?: string;
}

export const reportKeys = {
  all: (pid: string) => ["projects", pid, "report"] as const,
  prisma: (pid: string) => ["projects", pid, "report", "prisma"] as const,
  stats: (pid: string) => ["projects", pid, "report", "stats"] as const,
  methods: (pid: string) => ["projects", pid, "report", "methods"] as const,
  audit: (pid: string, filters: AuditFilters) =>
    ["projects", pid, "report", "audit", filters] as const,
};

export const prismaQuery = (pid: string) =>
  queryOptions({
    queryKey: reportKeys.prisma(pid),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/v1/projects/{pid}/prisma", { signal, params: { path: { pid } } })),
  });

export async function updatePrismaManual(pid: string, body: PrismaManualIn) {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/prisma/manual", { params: { path: { pid } }, body }),
  );
}

export type PrismaFormat = "svg" | "png" | "pdf";

/** The diagram as a file; `inline` shows the SVG in the page instead of downloading it. */
export function prismaUrl(pid: string, format: PrismaFormat, inline = false): string {
  return `/api/v1/projects/${pid}/prisma.${format}${inline ? "?inline=true" : ""}`;
}

export const statsQuery = (pid: string) =>
  queryOptions({
    queryKey: reportKeys.stats(pid),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/v1/projects/{pid}/stats", { signal, params: { path: { pid } } })),
  });

const clean = (filters: AuditFilters) =>
  Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) as AuditFilters;

export const auditQuery = (pid: string, filters: AuditFilters) =>
  infiniteQueryOptions({
    queryKey: reportKeys.audit(pid, clean(filters)),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ signal, pageParam }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/audit", {
          signal,
          params: { path: { pid }, query: { ...clean(filters), cursor: pageParam, limit: 50 } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });

export function auditCsvUrl(pid: string, filters: AuditFilters): string {
  const query = new URLSearchParams(clean(filters) as Record<string, string>).toString();
  return `/api/v1/projects/${pid}/audit.csv${query ? `?${query}` : ""}`;
}

export const methodsQuery = (pid: string) =>
  queryOptions({
    queryKey: reportKeys.methods(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/methods-text", { signal, params: { path: { pid } } }),
      ),
  });

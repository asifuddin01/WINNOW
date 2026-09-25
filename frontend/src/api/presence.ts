import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type PresentMember = components["schemas"]["PresentMember"];
export type PresenceStage = PresentMember["stage"];

export const presenceKey = (pid: string) => ["projects", pid, "presence"] as const;

/** Who else is screening: looked at every 30 seconds, as often as screeners say so. */
export const presenceQuery = (pid: string) =>
  queryOptions({
    queryKey: presenceKey(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/presence", { signal, params: { path: { pid } } }),
      ),
    refetchInterval: 30_000,
  });

export async function announcePresence(pid: string, stage: PresenceStage): Promise<void> {
  unwrap(
    await api.PUT("/api/v1/projects/{pid}/presence", {
      params: { path: { pid } },
      body: { stage },
    }),
  );
}

export async function withdrawPresence(pid: string): Promise<void> {
  unwrap(await api.DELETE("/api/v1/projects/{pid}/presence", { params: { path: { pid } } }));
}

import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type AdminUser = components["schemas"]["AdminUserOut"];
export type InstanceSettings = components["schemas"]["InstanceSettingsOut"];
export type InstanceSettingsPatch = components["schemas"]["InstanceSettingsPatch"];
export type Health = components["schemas"]["HealthOut"];

export const adminKeys = {
  all: ["admin"] as const,
  users: (q: string) => ["admin", "users", q] as const,
  settings: ["admin", "settings"] as const,
  health: ["admin", "health"] as const,
};

export const adminUsersQuery = (q: string) =>
  infiniteQueryOptions({
    queryKey: adminKeys.users(q),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ signal, pageParam }) =>
      unwrap(
        await api.GET("/api/v1/admin/users", {
          signal,
          params: { query: { q, cursor: pageParam, limit: 50 } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });

export const instanceSettingsQuery = queryOptions({
  queryKey: adminKeys.settings,
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/admin/settings", { signal })),
});

export const healthQuery = queryOptions({
  queryKey: adminKeys.health,
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/admin/health", { signal })),
  refetchInterval: 15_000,
});

type UserAction = "disable" | "enable" | "reset-2fa" | "sign-out";

export async function actOnUser(uid: string, action: UserAction): Promise<void> {
  const path = {
    disable: "/api/v1/admin/users/{uid}/disable",
    enable: "/api/v1/admin/users/{uid}/enable",
    "reset-2fa": "/api/v1/admin/users/{uid}/reset-2fa",
    "sign-out": "/api/v1/admin/users/{uid}/sign-out",
  } as const;
  unwrap(await api.POST(path[action], { params: { path: { uid } } }));
}

export async function updateInstanceSettings(body: InstanceSettingsPatch) {
  return unwrap(await api.PATCH("/api/v1/admin/settings", { body }));
}

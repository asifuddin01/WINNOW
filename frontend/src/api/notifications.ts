import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Notice = components["schemas"]["NotificationOut"];
export type NotificationSettings = components["schemas"]["NotificationSettings"];

export const noticeKeys = {
  all: ["notifications"] as const,
  list: ["notifications", "list"] as const,
  unread: ["notifications", "unread"] as const,
  settings: ["notifications", "settings"] as const,
};

export const noticesQuery = queryOptions({
  queryKey: noticeKeys.list,
  queryFn: async ({ signal }) =>
    unwrap(await api.GET("/api/v1/notifications", { signal, params: { query: { limit: 20 } } })),
});

/** The count on the bell: looked at every minute and whenever the tab comes back. */
export const unreadQuery = queryOptions({
  queryKey: noticeKeys.unread,
  queryFn: async ({ signal }) => unwrap(await api.GET("/api/v1/notifications/unread", { signal })),
  refetchInterval: 60_000,
  refetchOnWindowFocus: true,
});

export const noticeSettingsQuery = queryOptions({
  queryKey: noticeKeys.settings,
  queryFn: async ({ signal }) =>
    unwrap(await api.GET("/api/v1/notifications/settings", { signal })),
});

export async function markRead(id: string): Promise<void> {
  unwrap(await api.POST("/api/v1/notifications/{nid}/read", { params: { path: { nid: id } } }));
}

export async function markAllRead(): Promise<void> {
  unwrap(await api.POST("/api/v1/notifications/read-all"));
}

export async function updateNoticeSettings(body: NotificationSettings) {
  return unwrap(await api.PUT("/api/v1/notifications/settings", { body }));
}

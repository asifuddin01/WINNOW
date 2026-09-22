import { QueryClient } from "@tanstack/react-query";
import { describe, expect, test } from "vitest";

import { api } from "@/api/client";
import { authKeys, safeRedirect, signIn, signOut } from "@/api/auth";
import { CSRF, USER, mockApi } from "@/test/api";

describe("safeRedirect", () => {
  test.each([
    ["/account", "/account"],
    ["/p/123/screen/ta?x=1", "/p/123/screen/ta?x=1"],
    [undefined, "/"],
    ["https://evil.example/", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["javascript:alert(1)", "/"],
    ["/login", "/"],
    ["/reset/abc", "/"],
  ])("%s → %s", (target, expected) => {
    expect(safeRedirect(target)).toBe(expected);
  });
});

describe("CSRF", () => {
  test("writes carry the token; reads do not need one", async () => {
    const server = mockApi({
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    });
    await api.GET("/api/v1/readyz");
    expect(server.calls("GET /api/v1/auth/csrf")).toHaveLength(0);
    await api.POST("/api/v1/auth/logout");
    expect(server.calls("GET /api/v1/auth/csrf")).toHaveLength(1);
    expect(server.calls("POST /api/v1/auth/logout")[0]?.headers.get("X-CSRF-Token")).toBe(CSRF);
  });

  test("signing in adopts the session's new token and caches the user", async () => {
    const server = mockApi({
      "POST /api/v1/auth/login": { user: USER, csrf_token: "session-token" },
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    });
    const queryClient = new QueryClient();
    await signIn(queryClient, { email: USER.email, password: "a sturdy passphrase" });
    expect(queryClient.getQueryData(authKeys.me)).toEqual(USER);
    await signOut(queryClient);
    expect(server.calls("POST /api/v1/auth/logout")[0]?.headers.get("X-CSRF-Token")).toBe(
      "session-token",
    );
    expect(queryClient.getQueryData(authKeys.me)).toBeNull();
  });
});

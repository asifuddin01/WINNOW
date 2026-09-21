import { describe, expect, test } from "vitest";

import { ApiError, api, unwrap } from "@/api/client";
import { READY, problemResponse, stubFetch } from "@/test/api";

async function readyzError(): Promise<unknown> {
  try {
    unwrap(await api.GET("/api/v1/readyz"));
  } catch (error) {
    return error;
  }
  throw new Error("expected unwrap to throw");
}

describe("api client", () => {
  test("calls the API on the same origin with cookies, never a token", async () => {
    const fetch = stubFetch(() => Response.json(READY));
    expect(unwrap(await api.GET("/api/v1/readyz"))).toEqual(READY);
    const request = fetch.mock.calls[0]?.[0] as unknown as Request;
    expect(request.url).toBe(`${window.location.origin}/api/v1/readyz`);
    expect(request.credentials).toBe("same-origin");
    expect(request.headers.has("Authorization")).toBe(false);
  });

  test("turns a problem response into an ApiError with the request id", async () => {
    stubFetch(() =>
      problemResponse(503, {
        title: "Service Unavailable",
        detail: "A required service is unavailable.",
        request_id: "abc123",
      }),
    );
    const error = await readyzError();
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(503);
    expect(apiError.message).toBe("A required service is unavailable.");
    expect(apiError.requestId).toBe("abc123");
  });

  test("still reports failures whose body is not a problem", async () => {
    stubFetch(() => new Response("Bad Gateway", { status: 502 }));
    const error = (await readyzError()) as ApiError;
    expect(error.status).toBe(502);
    expect(error.problem).toBeNull();
    expect(error.requestId).toBeNull();
    expect(error.message).toBe("Request failed with status 502");
  });
});

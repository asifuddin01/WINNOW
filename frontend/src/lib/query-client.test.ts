import { describe, expect, test } from "vitest";

import { ApiError } from "@/api/client";
import { createQueryClient } from "@/lib/query-client";

describe("query retries", () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry as (
    failureCount: number,
    error: Error,
  ) => boolean;

  test("client errors are not retried", () => {
    expect(retry(0, new ApiError(404, null))).toBe(false);
    expect(retry(0, new ApiError(422, null))).toBe(false);
  });

  test("server and network failures are retried twice", () => {
    expect(retry(0, new ApiError(503, null))).toBe(true);
    expect(retry(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(retry(2, new TypeError("Failed to fetch"))).toBe(false);
  });
});

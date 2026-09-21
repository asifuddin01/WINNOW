import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { StatusBanner } from "@/components/layout/StatusBanner";
import { createQueryClient } from "@/lib/query-client";
import { problemResponse, stubFetch } from "@/test/api";

function renderBanner() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <StatusBanner />
    </QueryClientProvider>,
  );
}

describe("status banner", () => {
  test("stays silent while the server is ready", async () => {
    renderBanner();
    const fetch = vi.mocked(globalThis.fetch);
    await vi.waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  test("explains when the server cannot reach its dependencies", async () => {
    stubFetch(() =>
      problemResponse(503, { title: "Service Unavailable", checks: { database: "unavailable" } }),
    );
    renderBanner();
    expect(await screen.findByText(/cannot reach its server/)).toBeInTheDocument();
  });

  test("explains when the browser goes offline, and clears when it returns", async () => {
    renderBanner();
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(await screen.findByText(/You are offline/)).toBeInTheDocument();
    online.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByText(/You are offline/)).not.toBeInTheDocument();
  });
});

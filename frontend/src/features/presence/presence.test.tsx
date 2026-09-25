import { act, renderHook, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { usePresence } from "@/hooks/use-presence";
import { PROJECT, USER, mockApi, projectRoutes } from "@/test/api";
import { renderApp } from "@/test/render-app";

const base = `/api/v1/projects/${PROJECT.id}`;

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, value: state });
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => {
  vi.useRealTimers();
  setVisibility("visible");
});

describe("presence", () => {
  test("the overview says who is screening which stage, and nothing more", async () => {
    mockApi({
      "GET /api/v1/auth/me": USER,
      ...projectRoutes(),
      [`GET ${base}/presence`]: [
        { user_id: "u2", name: "Grace Hopper", stage: "title_abstract" },
        { user_id: "u3", name: "Hedy Lamarr", stage: "full_text" },
      ],
    });
    renderApp(`/p/${PROJECT.id}`);
    const now = await screen.findByRole("list", { name: "Screening now" });
    expect(within(now).getByText("Grace Hopper").parentElement).toHaveTextContent(
      "Grace Hopper is screening titles and abstracts",
    );
    expect(within(now).getByText("Hedy Lamarr").parentElement).toHaveTextContent(
      "Hedy Lamarr is screening full texts",
    );
  });

  test("nobody screening shows nothing", async () => {
    mockApi({ "GET /api/v1/auth/me": USER, ...projectRoutes(), [`GET ${base}/presence`]: [] });
    renderApp(`/p/${PROJECT.id}`);
    await screen.findByRole("heading", { name: PROJECT.title });
    expect(screen.queryByRole("list", { name: "Screening now" })).toBeNull();
  });

  test("a screening page says so every 30 seconds, and stops when hidden or closed", async () => {
    vi.useFakeTimers();
    const ok = () => new Response(null, { status: 204 });
    const server = mockApi({ [`PUT ${base}/presence`]: ok, [`DELETE ${base}/presence`]: ok });
    const { unmount } = renderHook(() => {
      usePresence(PROJECT.id, "title_abstract", true);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const put = server.calls(`PUT ${base}/presence`);
    expect(put).toHaveLength(1);
    expect(await put[0]?.json()).toEqual({ stage: "title_abstract" });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(server.calls(`PUT ${base}/presence`)).toHaveLength(2);

    act(() => {
      setVisibility("hidden");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(server.calls(`DELETE ${base}/presence`)).toHaveLength(1);
    expect(server.calls(`PUT ${base}/presence`)).toHaveLength(2); // quiet while hidden

    act(() => {
      setVisibility("visible");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(server.calls(`PUT ${base}/presence`)).toHaveLength(3);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(server.calls(`DELETE ${base}/presence`)).toHaveLength(2);
  });

  test("someone who does not screen says nothing", async () => {
    const server = mockApi({});
    renderHook(() => {
      usePresence(PROJECT.id, "full_text", false);
    });
    await Promise.resolve();
    expect(server.requests).toHaveLength(0);
  });
});

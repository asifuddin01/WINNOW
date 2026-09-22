import {
  Outlet,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "@/App";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorPage } from "@/components/layout/ErrorPage";
import { NotFoundPage } from "@/components/layout/NotFoundPage";
import { createQueryClient } from "@/lib/query-client";
import type { createAppRouter } from "@/router";
import { USER, mockApi } from "@/test/api";
import { renderApp } from "@/test/render-app";

function expectFooter() {
  const footer = screen.getByRole("contentinfo");
  expect(within(footer).getByRole("link", { name: "Asif" })).toHaveAttribute(
    "href",
    "https://asifuddin.com",
  );
}

describe("app shell", () => {
  beforeEach(() => {
    mockApi({ "GET /api/v1/auth/me": USER });
  });

  test("the dashboard renders inside the shell with the footer", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: "My reviews" })).toBeVisible();
    expect(await screen.findByText("No reviews yet")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expectFooter();
    expect(document.title).toBe("My reviews · Winnow");
  });

  test("navigation marks the current page", async () => {
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Workspace" });
    expect(within(nav).getByRole("link", { name: "My reviews" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByText("My reviews")).toHaveAttribute("aria-current", "page");
  });

  test("the skip link is the first thing a keyboard user reaches", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "My reviews" });
    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveFocus();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  test("collapsing the sidebar is remembered as a UI preference", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "My reviews" });
    await user.click(
      within(screen.getByRole("banner")).getByRole("button", { name: "Toggle sidebar" }),
    );
    expect(window.localStorage.getItem("winnow-sidebar")).toBe("collapsed");
    expect(document.cookie).toBe("");
  });

  test("an unknown address shows a not-found page with the footer", async () => {
    renderApp("/no/such/page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to my reviews" })).toHaveAttribute("href", "/");
    expectFooter();
  });
});

describe("error pages", () => {
  // Same composition as the real routes (root → _app layout → page), with pages that throw.
  function renderCrashingRoutes(path: string) {
    const root = createRootRoute({
      component: Outlet,
      errorComponent: ErrorPage,
      notFoundComponent: NotFoundPage,
    });
    const layout = createRoute({
      getParentRoute: () => root,
      id: "_app",
      component: () => (
        <AppShell>
          <Outlet />
        </AppShell>
      ),
      errorComponent: ErrorPage,
    });
    const crash = createRoute({
      getParentRoute: () => layout,
      path: "/crash",
      component: () => {
        throw new Error("boom inside the shell");
      },
    });
    const outside = createRoute({
      getParentRoute: () => root,
      path: "/outside",
      component: () => {
        throw new Error("boom outside the shell");
      },
    });
    const queryClient = createQueryClient();
    const router = createRouter({
      routeTree: root.addChildren([layout.addChildren([crash]), outside]),
      history: createMemoryHistory({ initialEntries: [path] }),
      defaultErrorComponent: ErrorPage,
    });
    render(
      <App
        router={router as unknown as ReturnType<typeof createAppRouter>}
        queryClient={queryClient}
      />,
    );
  }

  test("an error inside the shell keeps the shell and the footer", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderCrashingRoutes("/crash");
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeEnabled();
    expect(screen.queryByText("boom inside the shell")).not.toBeInTheDocument();
    expectFooter();
  });

  test("an error outside the shell is a standalone page, still with the footer", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderCrashingRoutes("/outside");
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Workspace" })).not.toBeInTheDocument();
    expect(screen.getByText(/Error id:/)).toHaveTextContent(/Error id: [0-9a-f]{16}/);
    expectFooter();
  });

  test("copying the error id confirms it", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    renderCrashingRoutes("/outside");
    await user.click(await screen.findByRole("button", { name: "Copy error id" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^[0-9a-f]{16}$/));
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});

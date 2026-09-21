import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { ApiError } from "@/api/client";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";

function Explode(): never {
  throw new ApiError(500, {
    type: "about:blank",
    title: "Internal Server Error",
    status: 500,
    request_id: "req-42",
  });
}

test("errors outside the router get the error page, the server's request id and the footer", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  render(
    <AppErrorBoundary>
      <Explode />
    </AppErrorBoundary>,
  );
  expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeVisible();
  expect(screen.getByText("req-42")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Asif" })).toHaveAttribute(
    "href",
    "https://asifuddin.com",
  );
});

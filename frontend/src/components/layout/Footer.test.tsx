import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Footer } from "@/components/layout/Footer";

test("credits Asif with a safe external link", () => {
  render(<Footer />);
  const footer = screen.getByRole("contentinfo");
  expect(footer).toHaveTextContent("Winnow · Built by Asif");
  const link = screen.getByRole("link", { name: "Asif" });
  expect(link).toHaveAttribute("href", "https://asifuddin.com");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link.getAttribute("rel")?.split(" ")).toEqual(
    expect.arrayContaining(["noopener", "noreferrer"]),
  );
});

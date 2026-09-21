import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { ThemeMenu } from "@/components/layout/ThemeMenu";
import { ThemeProvider } from "@/components/theme-provider";
import { THEME_STORAGE_KEY, useTheme } from "@/lib/theme";
import { installMatchMedia, setMedia } from "@/test/media";

function ShowTheme() {
  const { theme, resolvedTheme } = useTheme();
  return <output>{`${theme}:${resolvedTheme}`}</output>;
}

function renderTheme() {
  return render(
    <ThemeProvider>
      <ShowTheme />
      <ThemeMenu />
    </ThemeProvider>,
  );
}

const root = document.documentElement;

describe("theme", () => {
  test("follows the system preference by default", () => {
    installMatchMedia({ dark: true });
    renderTheme();
    expect(screen.getByRole("status")).toHaveTextContent("system:dark");
    expect(root).toHaveClass("dark");
    expect(root.style.colorScheme).toBe("dark");
  });

  test("tracks system changes while set to system", () => {
    renderTheme();
    expect(root).not.toHaveClass("dark");
    act(() => {
      setMedia({ dark: true });
    });
    expect(root).toHaveClass("dark");
  });

  test("an explicit choice overrides the system and is remembered", async () => {
    installMatchMedia({ dark: true });
    const user = userEvent.setup();
    renderTheme();
    await user.click(screen.getByRole("button", { name: "Colour theme: System" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Light" }));
    expect(screen.getByRole("status")).toHaveTextContent("light:light");
    expect(root).not.toHaveClass("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    act(() => {
      setMedia({ dark: false });
      setMedia({ dark: true });
    });
    expect(root).not.toHaveClass("dark");
  });

  test("restores a saved theme and ignores garbage", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    const { unmount } = renderTheme();
    expect(screen.getByRole("status")).toHaveTextContent("dark:dark");
    unmount();
    window.localStorage.setItem(THEME_STORAGE_KEY, "<script>");
    renderTheme();
    expect(screen.getByRole("status")).toHaveTextContent("system:light");
  });

  test("useTheme outside the provider is a programming error", () => {
    expect(() => render(<ShowTheme />)).toThrow("useTheme must be used inside <ThemeProvider>");
  });
});

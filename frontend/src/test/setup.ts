import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, vi } from "vitest";

import { forgetCsrfToken } from "@/api/csrf";
import { mockApi } from "@/test/api";
import { installMatchMedia } from "@/test/media";

// Route code loads lazily; slower machines (containers, CI) need more than the 1 s default.
configure({ asyncUtilTimeout: 3000 });

beforeEach(() => {
  installMatchMedia();
  // jsdom does not implement scrolling; the router's scroll restoration calls it.
  window.scrollTo = () => undefined;
  window.localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.removeAttribute("style");
  forgetCsrfToken();
  // A healthy instance with nobody signed in; tests override the routes they need.
  mockApi();
});

afterEach(() => {
  // Sonner keeps toasts in module state; one test's toast must not appear in the next.
  toast.dismiss();
  cleanup();
  vi.unstubAllGlobals();
});

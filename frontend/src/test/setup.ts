import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, vi } from "vitest";

import { forgetCsrfToken } from "@/api/csrf";
import "@/i18n";
import { mockApi } from "@/test/api";
import { installDomStubs } from "@/test/dom";
import { installMatchMedia } from "@/test/media";

// Route code loads lazily and the suite runs several files at once; slower machines
// (containers, CI) need well over the 1 s default.
configure({ asyncUtilTimeout: 6000 });

beforeEach(() => {
  installMatchMedia();
  installDomStubs();
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

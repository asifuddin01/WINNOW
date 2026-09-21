import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { READY, stubFetch } from "@/test/api";
import { installMatchMedia } from "@/test/media";

beforeEach(() => {
  installMatchMedia();
  // jsdom does not implement scrolling; the router's scroll restoration calls it.
  window.scrollTo = () => undefined;
  window.localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.removeAttribute("style");
  // Every API call must be stubbed explicitly; this default answers the readiness poll.
  stubFetch(() => Response.json(READY));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

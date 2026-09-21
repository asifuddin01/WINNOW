import "@/styles/globals.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { createQueryClient } from "@/lib/query-client";
import { createAppRouter } from "@/router";

const queryClient = createQueryClient();
const router = createAppRouter(queryClient);
const container = document.getElementById("root");
if (!container) throw new Error("index.html is missing #root");

createRoot(container).render(
  <StrictMode>
    <AppErrorBoundary>
      <App router={router} queryClient={queryClient} />
    </AppErrorBoundary>
  </StrictMode>,
);

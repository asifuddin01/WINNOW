import type { ReactNode } from "react";

import { BrandMark, Wordmark } from "@/components/layout/Brand";
import { Footer } from "@/components/layout/Footer";
import { SkipLink } from "@/components/layout/SkipLink";

/** Frame for pages outside the app shell (errors, not found, later sign-in): brand, content, footer. */
export function StandalonePage({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col">
      <SkipLink />
      <header className="flex h-14 items-center gap-2 px-4">
        <a href="/" className="flex items-center gap-2 rounded-md focus-visible:outline-2">
          <BrandMark />
          <Wordmark />
        </a>
      </header>
      <main id="main" tabIndex={-1} className="flex flex-1 flex-col outline-none">
        {children}
      </main>
      <Footer />
    </div>
  );
}

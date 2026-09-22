import type { ReactNode } from "react";

import { StandalonePage } from "@/components/layout/StandalonePage";

/** A narrow card centred on a standalone page, for sign-in and the other account pages. */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <StandalonePage>
      <div className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center">
        <section
          aria-labelledby="auth-title"
          className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-xs sm:p-8"
        >
          <h1 id="auth-title" className="text-xl font-semibold tracking-tight">
            {title}
          </h1>
          {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div>}
        </section>
      </div>
    </StandalonePage>
  );
}

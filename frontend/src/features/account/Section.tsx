import { useId, type ReactNode } from "react";

/** One titled block of the account page. */
export function Section({
  title,
  description,
  aside,
  children,
}: {
  title: string;
  description?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="rounded-xl border border-border bg-card p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id={id} className="text-base font-semibold">
            {title}
          </h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {aside}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

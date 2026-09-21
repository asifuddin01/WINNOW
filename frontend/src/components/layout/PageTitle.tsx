import { useEffect } from "react";

import { useRouteTitles } from "@/hooks/use-route-titles";

export function Breadcrumbs() {
  const titles = useRouteTitles();
  if (titles.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {titles.map((title, index) => {
          const isLast = index === titles.length - 1;
          return (
            <li key={`${index}-${title}`} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <span aria-hidden="true">/</span>}
              <span
                className={isLast ? "truncate font-medium text-foreground" : "truncate"}
                aria-current={isLast ? "page" : undefined}
              >
                {title}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Keeps the browser tab title in step with the current page. */
export function DocumentTitle() {
  const titles = useRouteTitles();
  const page = titles.at(-1);
  useEffect(() => {
    document.title = page ? `${page} · Winnow` : "Winnow";
  }, [page]);
  return null;
}

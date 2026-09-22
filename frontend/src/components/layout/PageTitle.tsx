import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { projectQuery } from "@/api/projects";
import { useCrumbs, useRouteTitles } from "@/hooks/use-route-titles";
import { cn } from "@/lib/utils";

export function Breadcrumbs() {
  const crumbs = useCrumbs();
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li key={crumb.key} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <span aria-hidden="true">/</span>}
              <span
                className={cn("truncate", isLast && "font-medium text-foreground")}
                aria-current={isLast ? "page" : undefined}
              >
                {crumb.projectId ? <ProjectCrumb pid={crumb.projectId} /> : crumb.title}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** The review's own title, from the cache the project route filled. */
function ProjectCrumb({ pid }: { pid: string }) {
  const { data: project } = useQuery(projectQuery(pid));
  return <>{project?.title ?? "Review"}</>;
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

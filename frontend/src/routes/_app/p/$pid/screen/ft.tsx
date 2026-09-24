import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";

import { fulltextSummaryQuery } from "@/api/fulltext";
import { projectQuery } from "@/api/projects";
import { FulltextOverview } from "@/features/fulltext/FulltextOverview";
import { ScreeningPage } from "@/features/screening/ScreeningPage";
import { fullTextSearch } from "@/lib/search";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/p/$pid/screen/ft")({
  validateSearch: fullTextSearch,
  component: FullTextScreening,
  staticData: { title: "Full text" },
});

/** Guide 8.8: full-text screening, and the PDFs it needs. Viewers see the PDFs. */
function FullTextScreening() {
  const { pid } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  const { data: project } = useQuery(projectQuery(pid));
  const { data: summary } = useQuery(fulltextSummaryQuery(pid));
  if (!project) return null;
  const screens = project.permissions.includes("screen");
  const pdfs = search.view === "pdfs" || !screens;

  const tab = (active: boolean) =>
    cn(
      "rounded-md px-3 py-1.5 text-sm font-medium",
      active ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:bg-accent",
    );

  return (
    <div className="grid content-start">
      <nav aria-label="Full text" className="flex gap-1 px-4 pt-4 md:px-6">
        {screens && (
          <Link
            to="/p/$pid/screen/ft"
            params={{ pid }}
            className={tab(!pdfs)}
            aria-current={!pdfs ? "page" : undefined}
          >
            Screen
          </Link>
        )}
        <Link
          to="/p/$pid/screen/ft"
          params={{ pid }}
          search={{ view: "pdfs" }}
          className={tab(pdfs)}
          aria-current={pdfs ? "page" : undefined}
        >
          PDFs
          {summary && summary.missing > 0 && (
            <>
              {" "}
              <span className="text-muted-foreground tabular-nums">
                ({summary.missing.toLocaleString()} missing)
              </span>
            </>
          )}
        </Link>
      </nav>
      {pdfs ? (
        <div className="grid gap-4 px-4 py-6 md:px-6">
          <h1 className="text-lg font-semibold tracking-tight">Full-text PDFs</h1>
          <FulltextOverview pid={pid} />
        </div>
      ) : (
        <ScreeningPage
          pid={pid}
          stage="full_text"
          view={{ sort: search.sort ?? "relevance", q: search.q ?? "" }}
          onViewChange={(view) => {
            void navigate({
              to: "/p/$pid/screen/ft",
              params: { pid },
              search: {
                ...(view.sort !== "relevance" ? { sort: view.sort } : {}),
                ...(view.q ? { q: view.q } : {}),
              },
              replace: true,
            });
          }}
        />
      )}
    </div>
  );
}

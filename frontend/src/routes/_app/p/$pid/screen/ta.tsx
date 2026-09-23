import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { ScreeningPage } from "@/features/screening/ScreeningPage";
import { screenSearch } from "@/lib/search";

export const Route = createFileRoute("/_app/p/$pid/screen/ta")({
  validateSearch: screenSearch,
  component: TitleAbstractScreening,
  staticData: { title: "Screen" },
});

function TitleAbstractScreening() {
  const { pid } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  return (
    <ScreeningPage
      pid={pid}
      stage="title_abstract"
      view={{ sort: search.sort ?? "relevance", q: search.q ?? "" }}
      onViewChange={(view) => {
        void navigate({
          to: "/p/$pid/screen/ta",
          params: { pid },
          search: {
            ...(view.sort !== "relevance" ? { sort: view.sort } : {}),
            ...(view.q ? { q: view.q } : {}),
          },
          replace: true,
        });
      }}
    />
  );
}

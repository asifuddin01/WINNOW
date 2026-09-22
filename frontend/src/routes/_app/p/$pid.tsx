import { useQuery } from "@tanstack/react-query";
import { Outlet, createFileRoute, notFound } from "@tanstack/react-router";

import { isApiError } from "@/api/auth";
import { loadProject, projectQuery } from "@/api/projects";
import { NotFoundPage } from "@/components/layout/NotFoundPage";

export const Route = createFileRoute("/_app/p/$pid")({
  loader: async ({ context, params }) => {
    try {
      await loadProject(context.queryClient, params.pid);
    } catch (error) {
      // A review you cannot see answers 404, whether or not it exists (guide 7).
      if (isApiError(error) && error.status === 404) notFound({ throw: true });
      throw error;
    }
  },
  component: ProjectLayout,
  notFoundComponent: () => (
    <NotFoundPage
      title="Review not found"
      detail="It may have been deleted, or you may not be a member of it."
    />
  ),
  staticData: { crumb: "project" },
});

function ProjectLayout() {
  const { pid } = Route.useParams();
  // Keeps the project in the cache for the pages below, and the title in the breadcrumb.
  useQuery(projectQuery(pid));
  return <Outlet />;
}

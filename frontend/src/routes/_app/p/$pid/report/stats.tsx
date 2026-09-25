import { createFileRoute } from "@tanstack/react-router";

import { StatsView } from "@/features/report/StatsView";

export const Route = createFileRoute("/_app/p/$pid/report/stats")({
  component: StatsPage,
  staticData: { title: "Statistics" },
});

function StatsPage() {
  const { pid } = Route.useParams();
  return <StatsView pid={pid} />;
}

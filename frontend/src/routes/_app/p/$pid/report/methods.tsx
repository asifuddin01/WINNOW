import { createFileRoute } from "@tanstack/react-router";

import { MethodsView } from "@/features/report/MethodsView";

export const Route = createFileRoute("/_app/p/$pid/report/methods")({
  component: MethodsPage,
  staticData: { title: "Methods" },
});

function MethodsPage() {
  const { pid } = Route.useParams();
  return <MethodsView pid={pid} />;
}

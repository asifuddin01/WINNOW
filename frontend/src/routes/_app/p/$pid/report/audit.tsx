import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { projectQuery } from "@/api/projects";
import { AuditView } from "@/features/report/AuditView";

export const Route = createFileRoute("/_app/p/$pid/report/audit")({
  component: AuditPage,
  staticData: { title: "Audit log" },
});

function AuditPage() {
  const { pid } = Route.useParams();
  const { data: project } = useQuery(projectQuery(pid));
  if (!project) return null;
  if (!project.permissions.includes("edit_settings")) {
    return (
      <p className="text-sm text-muted-foreground">
        The audit log is for the review&apos;s owners and admins.
      </p>
    );
  }
  return <AuditView pid={pid} />;
}

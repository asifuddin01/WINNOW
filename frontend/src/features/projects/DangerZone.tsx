import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { meQuery } from "@/api/auth";
import {
  deleteProject,
  leaveProject,
  membersQuery,
  projectKeys,
  transferProject,
  updateProject,
  type Project,
} from "@/api/projects";
import { SelectField } from "@/components/forms/SelectField";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/features/projects/ConfirmDialog";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

/** Archive, hand on or delete a review — and leave one that is not yours (guide 8.2). */
export function DangerZone({ project }: { project: Project }) {
  const pid = project.id;
  const navigate = useNavigate();
  const { data: me } = useQuery(meQuery);
  const { data: members } = useQuery(membersQuery(pid));
  const canDelete = project.permissions.includes("delete_project");
  const canArchive = project.permissions.includes("edit_settings");
  const archived = project.status === "archived";

  const archive = useProjectMutation(
    (status: Project["status"]) => updateProject(pid, { status }),
    { invalidate: [projectKeys.detail(pid), projectKeys.list], success: "Status changed." },
  );
  const hand_on = useProjectMutation((uid: string) => transferProject(pid, uid), {
    invalidate: [projectKeys.detail(pid), projectKeys.members(pid)],
    success: "The review has a new owner.",
  });
  const remove = useProjectMutation(() => deleteProject(pid), {
    invalidate: [projectKeys.list],
    success: "Review deleted.",
  });
  const leave = useProjectMutation(() => leaveProject(pid), {
    invalidate: [projectKeys.list],
    success: "You left the review.",
  });
  const goHome = () => void navigate({ to: "/" });

  const candidates = (members?.items ?? [])
    .filter((member) => member.user.id !== me?.id)
    .map((member) => ({ value: member.user.id, label: member.user.name }));
  const [heir, setHeir] = useState("");

  return (
    <div className="grid gap-4 rounded-xl border border-destructive/40 p-5">
      <div>
        <h2 className="text-base font-semibold">Danger zone</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          These change the review for everyone on it.
        </p>
      </div>

      {canArchive && (
        <Row
          title={archived ? "Restore this review" : "Archive this review"}
          description={
            archived
              ? "Put it back into setup so the team can work on it again."
              : "Keep everything, but mark the review as finished with. You can restore it later."
          }
          action={
            <Button
              variant="outline"
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate(archived ? "setup" : "archived");
              }}
            >
              {archived ? "Restore" : "Archive"}
            </Button>
          }
        />
      )}

      {canDelete && candidates.length > 0 && (
        <Row
          title="Hand the review to someone else"
          description="They become the owner; you stay on as an admin."
          action={
            <div className="flex flex-wrap items-end gap-2">
              <SelectField
                label="New owner"
                value={heir}
                className="w-48"
                options={[{ value: "", label: "Choose a member" }, ...candidates]}
                onChange={setHeir}
              />
              <ConfirmDialog
                trigger={
                  <Button variant="outline" disabled={!heir}>
                    Transfer
                  </Button>
                }
                title="Hand over this review?"
                description="Only the new owner can delete the review or transfer it again. You keep admin access."
                confirmLabel="Transfer"
                onConfirm={() => {
                  hand_on.mutate(heir);
                }}
              />
            </div>
          }
        />
      )}

      {project.membership.role !== "owner" && (
        <Row
          title="Leave this review"
          description="You lose access. Decisions you have already made stay with the review."
          action={
            <ConfirmDialog
              trigger={<Button variant="outline">Leave</Button>}
              title="Leave this review?"
              description="You will need a new invitation to come back."
              confirmLabel="Leave"
              destructive
              onConfirm={() => {
                leave.mutate(undefined, { onSuccess: goHome });
              }}
            />
          }
        />
      )}

      {canDelete && (
        <Row
          title="Delete this review"
          description="Everything in it — criteria, records, decisions — goes with it."
          action={
            <ConfirmDialog
              trigger={<Button variant="destructive">Delete review</Button>}
              title="Delete this review?"
              description="This cannot be undone from the app. Ask your administrator if you delete one by mistake."
              confirmLabel="Delete review"
              confirmPhrase={project.title}
              destructive
              onConfirm={() => {
                remove.mutate(undefined, { onSuccess: goHome });
              }}
            />
          }
        />
      )}
    </div>
  );
}

function Row({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 first:border-0 first:pt-0">
      <div className="min-w-60 flex-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}

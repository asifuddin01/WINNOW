import { useQuery } from "@tanstack/react-query";
import { CopyIcon, MailIcon, UserMinusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { authOptionsQuery, meQuery } from "@/api/auth";
import {
  invitesQuery,
  inviteMember,
  membersQuery,
  projectKeys,
  removeMember,
  revokeInvite,
  updateMember,
  type AssignableRole,
  type Project,
} from "@/api/projects";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/features/projects/ConfirmDialog";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { ROLE_DESCRIPTIONS, ROLES } from "@/features/projects/wording";
import { initials, timeAgo } from "@/lib/format";

const ASSIGNABLE: AssignableRole[] = ["admin", "reviewer", "viewer"];
const ROLE_OPTIONS = ASSIGNABLE.map((value) => ({ value, label: ROLES[value] }));

/** Clipboard access is missing on plain-HTTP origins; the link stays selectable either way. */
async function copyLink(link: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(link);
    toast.success("Link copied.");
  } catch {
    toast.error("Copying failed. Select the link and copy it yourself.");
  }
}

/** Who is on the review, what they may do, and who has been invited (guide 8.2). */
export function TeamEditor({ project }: { project: Project }) {
  const pid = project.id;
  const canManage = project.permissions.includes("manage_members");
  const { data: me } = useQuery(meQuery);
  const { data: options } = useQuery(authOptionsQuery);
  const { data: members } = useQuery(membersQuery(pid));
  const invalidate = [projectKeys.members(pid), projectKeys.detail(pid)];
  const changeRole = useProjectMutation(
    ({ uid, role }: { uid: string; role: AssignableRole }) => updateMember(pid, uid, { role }),
    { invalidate, success: "Role changed." },
  );
  const remove = useProjectMutation((uid: string) => removeMember(pid, uid), {
    invalidate,
    success: "Removed from the review.",
  });

  return (
    <div className="grid gap-6">
      <ul className="grid gap-2">
        {(members?.items ?? []).map((member) => {
          const isMe = member.user.id === me?.id;
          const editable = canManage && member.role !== "owner";
          return (
            <li
              key={member.user.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3"
            >
              <span
                aria-hidden="true"
                className="flex size-9 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground"
              >
                {initials(member.user.name)}
              </span>
              <span className="min-w-40 flex-1">
                <span className="block text-sm font-medium">
                  {member.user.name}
                  {isMe && <span className="text-muted-foreground"> (you)</span>}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {member.user.email ?? `Joined ${timeAgo(member.joined_at)}`}
                </span>
              </span>
              {editable ? (
                <SelectField
                  label={`Role for ${member.user.name}`}
                  value={member.role as AssignableRole}
                  options={ROLE_OPTIONS}
                  className="w-40"
                  onChange={(role) => {
                    changeRole.mutate({ uid: member.user.id, role });
                  }}
                />
              ) : (
                <Badge variant="secondary">{ROLES[member.role]}</Badge>
              )}
              {editable && (
                <ConfirmDialog
                  trigger={
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-muted-foreground"
                      aria-label={`Remove ${member.user.name}`}
                    >
                      <UserMinusIcon aria-hidden="true" /> Remove
                    </Button>
                  }
                  title={`Remove ${member.user.name}?`}
                  description="They lose access to this review straight away. Anything they have already decided stays."
                  confirmLabel="Remove"
                  destructive
                  onConfirm={() => {
                    remove.mutate(member.user.id);
                  }}
                />
              )}
            </li>
          );
        })}
      </ul>

      {canManage &&
        (options?.single_user ? (
          <p className="text-sm text-muted-foreground">
            This Winnow instance is set up for one person, so there is nobody to invite.
          </p>
        ) : (
          <InviteBox project={project} emailWorks={options?.email_enabled ?? false} />
        ))}
    </div>
  );
}

function InviteBox({ project, emailWorks }: { project: Project; emailWorks: boolean }) {
  const pid = project.id;
  const { data: invites = [] } = useQuery(invitesQuery(pid));
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AssignableRole>("reviewer");
  const [link, setLink] = useState<string | null>(null);
  const invalidate = [projectKeys.invites(pid)];
  const invite = useProjectMutation(
    (values: { email: string; role: AssignableRole }) =>
      inviteMember(pid, values.email, values.role),
    { invalidate },
  );
  const withdraw = useProjectMutation((iid: string) => revokeInvite(pid, iid), {
    invalidate,
    success: "Invitation withdrawn.",
  });

  return (
    <div className="grid gap-4">
      <form
        className="grid gap-3 rounded-lg border border-dashed border-input p-4 sm:grid-cols-[1fr_12rem] sm:items-end xl:grid-cols-[1fr_12rem_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          if (!email.trim()) return;
          invite.mutate(
            { email: email.trim(), role },
            {
              onSuccess: (created) => {
                setEmail("");
                setLink(created.emailed ? null : created.link);
                toast.success(
                  created.emailed
                    ? `Invitation sent to ${created.email}.`
                    : `Invitation created for ${created.email}.`,
                );
              },
            },
          );
        }}
      >
        <TextField
          label="Invite by email"
          type="email"
          autoComplete="off"
          placeholder="colleague@university.edu"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />
        <SelectField label="As" value={role} options={ROLE_OPTIONS} onChange={setRole} />
        <Button type="submit" disabled={invite.isPending} className="justify-self-start">
          <MailIcon aria-hidden="true" /> Send invitation
        </Button>
        <dl className="text-xs text-muted-foreground sm:col-span-2 xl:col-span-3">
          {ASSIGNABLE.map((value) => (
            <div key={value} className="flex gap-2">
              <dt className="min-w-16 font-medium text-foreground">{ROLES[value]}</dt>
              <dd>{ROLE_DESCRIPTIONS[value]}</dd>
            </div>
          ))}
        </dl>
      </form>

      {link && (
        <div className="grid gap-2 rounded-lg border border-border bg-muted/40 p-4">
          <p className="text-sm">
            {emailWorks
              ? "Here is the link, in case the email does not arrive."
              : "This instance sends no email yet, so pass this link on yourself. It only works for the invited address."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-background px-2 py-1 text-xs">
              {link}
            </code>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                void copyLink(link);
              }}
            >
              <CopyIcon aria-hidden="true" /> Copy link
            </Button>
          </div>
        </div>
      )}

      {invites.length > 0 && (
        <section aria-labelledby="pending-invites" className="grid gap-2">
          <h3 id="pending-invites" className="text-sm font-semibold">
            Invited, not joined yet
          </h3>
          <ul className="grid gap-2">
            {invites.map((pending) => (
              <li
                key={pending.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3 text-sm"
              >
                <span className="flex-1">{pending.email}</span>
                <Badge variant="outline">{ROLES[pending.role]}</Badge>
                <span className="text-xs text-muted-foreground">
                  {pending.expired ? "Expired" : `Expires ${timeAgo(pending.expires_at)}`}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-muted-foreground"
                  aria-label={`Withdraw the invitation to ${pending.email}`}
                  onClick={() => {
                    withdraw.mutate(pending.id);
                  }}
                >
                  Withdraw
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useId } from "react";

import { noticeKeys, noticeSettingsQuery, updateNoticeSettings } from "@/api/notifications";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Section } from "@/features/account/Section";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

/** Guide 8.17: the daily email digest is off unless you turn it on. */
export function NotificationsSection() {
  const id = useId();
  const { data } = useQuery(noticeSettingsQuery);
  const save = useProjectMutation((on: boolean) => updateNoticeSettings({ email_digest: on }), {
    invalidate: [noticeKeys.settings],
    success: "Saved.",
  });
  return (
    <div id="notifications">
      <Section
        title="Notifications"
        description="Conflicts to resolve, mentions in notes, invitations and finished imports appear under the bell at the top of every page."
      >
        <div className="flex items-start gap-3">
          <Switch
            id={`${id}-digest`}
            checked={data?.email_digest ?? false}
            disabled={!data || save.isPending}
            aria-describedby={`${id}-hint`}
            onCheckedChange={(on) => {
              save.mutate(on);
            }}
          />
          <div className="grid gap-1">
            <Label htmlFor={`${id}-digest`}>Email me a daily digest</Label>
            <p id={`${id}-hint`} className="text-sm text-muted-foreground">
              Once a morning, what is still unread from the day before. Nothing is sent on quiet
              days.
            </p>
          </div>
        </div>
      </Section>
    </div>
  );
}

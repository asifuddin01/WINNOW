import { api, unwrap } from "@/api/client";
import { projectKeys, type Project } from "@/api/projects";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Section } from "@/features/account/Section";
import { useProjectMutation } from "@/features/projects/use-project-mutation";

async function setKeepBlind(pid: string, keepBlind: boolean): Promise<void> {
  unwrap(
    await api.PATCH("/api/v1/projects/{pid}/membership", {
      params: { path: { pid } },
      body: { keep_blind: keepBlind },
    }),
  );
}

/**
 * Guide 7: owners and admins may look at other people's decisions, which breaks their own
 * blinding. This keeps them blind unless they say otherwise.
 */
export function MyScreeningPreferences({ project }: { project: Project }) {
  const canSeeOthers = project.permissions.includes("see_others_while_blind");
  const keepBlind = useProjectMutation((value: boolean) => setKeepBlind(project.id, value), {
    invalidate: [projectKeys.detail(project.id)],
    success: "Saved.",
  });
  if (!canSeeOthers || !project.settings.blind_mode) return null;

  return (
    <Section title="Just for you" description="This setting affects nobody else on the review.">
      <div className="flex items-start gap-3">
        <Switch
          id="keep-blind"
          checked={project.membership.keep_blind}
          aria-describedby="keep-blind-hint"
          onCheckedChange={(checked) => {
            keepBlind.mutate(checked);
          }}
        />
        <div className="grid gap-1">
          <Label htmlFor="keep-blind">Keep me blind too</Label>
          <p id="keep-blind-hint" className="text-xs text-muted-foreground">
            Your role lets you see other reviewers' decisions while blind screening is on. Leave
            this on and Winnow hides them from you as well, so your own screening stays independent.
          </p>
        </div>
      </div>
    </Section>
  );
}

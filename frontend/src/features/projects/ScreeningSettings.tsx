import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { authOptionsQuery } from "@/api/auth";
import { projectKeys, updateSettings, type Project, type ProjectSettings } from "@/api/projects";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { suggestionsExportUrl } from "@/api/llm";

const REVIEWERS = [1, 2, 3, 4, 5].map((n) => ({
  value: String(n),
  label: n === 1 ? "1 reviewer" : `${n} reviewers`,
}));

/** Everything in guide 6.2: how many reviewers, blinding, reasons, ranking, stopping. */
export function ScreeningSettings({ project }: { project: Project }) {
  const { data: options } = useQuery(authOptionsQuery);
  const [draft, setDraft] = useState<ProjectSettings>(project.settings);
  const isOwner = project.membership.role === "owner";
  const save = useProjectMutation(
    (settings: ProjectSettings) => updateSettings(project.id, settings),
    {
      invalidate: [projectKeys.detail(project.id)],
      success: "Settings saved.",
    },
  );
  const set = <K extends keyof ProjectSettings>(key: K, value: ProjectSettings[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const changed = JSON.stringify(draft) !== JSON.stringify(project.settings);

  return (
    <form
      className="grid gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(draft);
      }}
    >
      <Toggle
        id="blind-mode"
        label="Blind screening"
        hint="Reviewers cannot see each other's decisions until conflicts are resolved. Turning this off is recorded in the audit log."
        checked={draft.blind_mode}
        onChange={(checked) => {
          set("blind_mode", checked);
        }}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Reviewers per record: title and abstract"
          value={String(draft.reviewers_per_record_ta)}
          options={REVIEWERS}
          onChange={(value) => {
            set("reviewers_per_record_ta", Number(value));
          }}
        />
        <SelectField
          label="Reviewers per record: full text"
          value={String(draft.reviewers_per_record_ft)}
          options={REVIEWERS}
          onChange={(value) => {
            set("reviewers_per_record_ft", Number(value));
          }}
        />
        <SelectField
          label="A “maybe” counts as"
          value={draft.maybe_counts_as}
          options={[
            { value: "include", label: "Include — it goes on to full text" },
            { value: "maybe", label: "Maybe — the team decides later" },
          ]}
          onChange={(value) => {
            set("maybe_counts_as", value);
          }}
        />
        <SelectField
          label="Who screens which records"
          value={draft.assignment}
          options={[
            { value: "all", label: "Everyone screens every record" },
            { value: "split", label: "Share records out between reviewers" },
          ]}
          onChange={(value) => {
            set("assignment", value);
          }}
        />
      </div>
      <Toggle
        id="reason-ta"
        label="Require a reason when excluding at title and abstract"
        checked={draft.require_reason_on_exclude_ta}
        onChange={(checked) => {
          set("require_reason_on_exclude_ta", checked);
        }}
      />
      <Toggle
        id="reason-ft"
        label="Require a reason when excluding at full text"
        hint="PRISMA 2020 asks for exclusion reasons at the full-text stage."
        checked={draft.require_reason_on_exclude_ft}
        onChange={(checked) => {
          set("require_reason_on_exclude_ft", checked);
        }}
      />
      <Toggle
        id="highlight"
        label="Highlight keywords while screening"
        checked={draft.highlight_keywords}
        onChange={(checked) => {
          set("highlight_keywords", checked);
        }}
      />
      <Toggle
        id="ranking"
        label="Order the queue by relevance as you screen"
        hint="Winnow learns from your decisions on this server; nothing leaves it."
        checked={draft.ranking_enabled}
        onChange={(checked) => {
          set("ranking_enabled", checked);
        }}
      />
      <Toggle
        id="llm"
        label="AI suggestions with reasons"
        hint={
          !options?.llm_available
            ? "This Winnow instance has no AI provider set up, so this stays off."
            : !isOwner && !project.settings.llm_assist_enabled
              ? "Sending records to an AI provider is the owner's decision: only they can turn this on."
              : "When a reviewer asks, sends that record's title, abstract and keywords, and the criteria, to the configured provider. It never decides. Off by default."
        }
        disabled={!options?.llm_available || (!isOwner && !project.settings.llm_assist_enabled)}
        checked={draft.llm_assist_enabled}
        onChange={(checked) => {
          set("llm_assist_enabled", checked);
        }}
      />
      {project.settings.llm_assist_enabled && (
        <a
          href={suggestionsExportUrl(project.id)}
          download
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Download every AI suggestion (CSV), for reporting AI use in your methods
        </a>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Stopping rule"
          value={draft.stopping_rule.type}
          options={[
            { value: "consecutive_excludes", label: "Suggest stopping after a run of excludes" },
            { value: "none", label: "No suggestion" },
          ]}
          onChange={(value) => {
            set("stopping_rule", {
              ...draft.stopping_rule,
              type: value,
            });
          }}
        />
        {draft.stopping_rule.type === "consecutive_excludes" && (
          <TextField
            label="After this many excludes in a row"
            type="number"
            min={10}
            max={100000}
            value={draft.stopping_rule.n}
            onChange={(event) => {
              set("stopping_rule", { ...draft.stopping_rule, n: Number(event.target.value) });
            }}
          />
        )}
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!changed || save.isPending}>
          {save.isPending ? "Saving…" : "Save settings"}
        </Button>
        {changed && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setDraft(project.settings);
            }}
          >
            Discard changes
          </Button>
        )}
      </div>
    </form>
  );
}

function Toggle({
  id,
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className="flex items-start gap-3">
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        aria-describedby={hintId}
        onCheckedChange={onChange}
      />
      <div className="grid gap-1">
        <Label htmlFor={id}>{label}</Label>
        {hint && (
          <p id={hintId} className="text-xs text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

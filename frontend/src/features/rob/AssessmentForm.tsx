import { CheckIcon, Trash2Icon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { errorMessage } from "@/api/client";
import {
  chooseFinal,
  deleteAssessment,
  robKeys,
  saveAssessment,
  type Assessment,
  type AssessmentIn,
  type RobDomain,
  type RobTool,
} from "@/api/rob";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { JudgementMark } from "@/features/rob/JudgementMark";
import { answerLabel } from "@/features/rob/wording";
import { cn } from "@/lib/utils";

type Nested = Record<string, Record<string, string>>;

const NONE = "none";

/** My assessment of one study with one tool; a draft may be partial (guide 8.13). */
export function AssessmentForm({
  pid,
  rid,
  tool,
  mine,
  canAssess,
}: {
  pid: string;
  rid: string;
  tool: RobTool;
  mine: Assessment | undefined;
  canAssess: boolean;
}) {
  const id = useId();
  const [variantKey, setVariantKey] = useState(mine?.variant_key ?? tool.variants[0]?.key ?? "");
  const [answers, setAnswers] = useState<Nested>(mine?.answers ?? {});
  const [judgements, setJudgements] = useState<Nested>(mine?.judgements ?? {});
  const [support, setSupport] = useState<Record<string, string>>(mine?.support ?? {});
  const [overall, setOverall] = useState(mine?.overall ?? NONE);
  const variant = tool.variants.find((v) => v.key === variantKey) ?? tool.variants[0];

  const invalidate = [robKeys.all(pid)];
  const save = useProjectMutation(
    (status: AssessmentIn["status"]) =>
      saveAssessment(pid, rid, {
        tool_key: tool.key,
        variant_key: variantKey,
        answers,
        judgements,
        support,
        overall: overall === NONE ? null : overall,
        status,
      }),
    { invalidate, success: "Saved." },
  );
  const remove = useProjectMutation(() => deleteAssessment(pid, rid, tool.key), {
    invalidate,
    success: "Your assessment was deleted.",
  });

  if (!variant) return null;
  const overallChoices = variant.domains[0]?.axes[0]?.judgements ?? [];

  return (
    <form
      className="grid gap-5"
      aria-labelledby={`${id}-title`}
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate("submitted");
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id={`${id}-title`} className="text-base font-medium">
          Your assessment
          {mine && (
            <Badge variant={mine.status === "submitted" ? "default" : "secondary"} className="ml-2">
              {mine.status === "submitted" ? "Submitted" : "Draft"}
            </Badge>
          )}
        </h3>
        {tool.variants.length > 1 && (
          <SelectField
            label="Form"
            value={variantKey}
            options={tool.variants.map((v) => ({ value: v.key, label: v.name }))}
            onChange={setVariantKey}
            disabled={!canAssess}
          />
        )}
      </div>

      {variant.domains.map((domain) => (
        <DomainFields
          key={domain.key}
          domain={domain}
          disabled={!canAssess}
          answers={answers[domain.key] ?? {}}
          judgements={judgements[domain.key] ?? {}}
          support={support[domain.key] ?? ""}
          onAnswer={(question, answer) => {
            setAnswers((all) => ({
              ...all,
              [domain.key]: { ...all[domain.key], [question]: answer },
            }));
          }}
          onJudge={(axis, judgement) => {
            setJudgements((all) => ({
              ...all,
              [domain.key]: { ...all[domain.key], [axis]: judgement },
            }));
          }}
          onSupport={(text) => {
            setSupport((all) => ({ ...all, [domain.key]: text }));
          }}
        />
      ))}

      {overallChoices.length > 0 && (
        <div className="max-w-sm">
          <SelectField
            label="Overall judgement"
            value={overall}
            options={[
              { value: NONE, label: "Not given" },
              ...overallChoices.map((choice) => ({ value: choice.key, label: choice.label })),
            ]}
            onChange={setOverall}
            disabled={!canAssess}
          />
        </div>
      )}

      {save.isError && <FormAlert>{errorMessage(save.error)}</FormAlert>}
      {canAssess && (
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending}>
            <CheckIcon aria-hidden="true" /> Submit
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={save.isPending}
            onClick={() => {
              save.mutate("draft");
            }}
          >
            Save as draft
          </Button>
          {mine && (
            <Button
              type="button"
              variant="ghost"
              className="ml-auto text-destructive"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(undefined);
              }}
            >
              <Trash2Icon aria-hidden="true" /> Delete my assessment
            </Button>
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Submitting needs a judgement on every domain; a draft can be finished later.
      </p>
    </form>
  );
}

function DomainFields({
  domain,
  disabled,
  answers,
  judgements,
  support,
  onAnswer,
  onJudge,
  onSupport,
}: {
  domain: RobDomain;
  disabled: boolean;
  answers: Record<string, string>;
  judgements: Record<string, string>;
  support: string;
  onAnswer: (question: string, answer: string) => void;
  onJudge: (axis: string, judgement: string) => void;
  onSupport: (text: string) => void;
}) {
  const id = useId();
  return (
    <fieldset
      className="grid gap-4 rounded-xl border border-border bg-card p-4"
      disabled={disabled}
    >
      <legend className="px-1 text-sm font-semibold">{domain.name}</legend>
      {domain.questions.length > 0 && (
        <ol className="grid gap-3">
          {domain.questions.map((question) => (
            <li key={question.key}>
              <Choices
                legend={question.prompt}
                name={`${id}-${question.key}`}
                value={answers[question.key]}
                options={question.answers.map((answer) => ({
                  key: answer,
                  label: answerLabel(answer),
                }))}
                onChange={(answer) => {
                  onAnswer(question.key, answer);
                }}
              />
            </li>
          ))}
        </ol>
      )}
      {domain.axes.map((axis) => (
        <Choices
          key={axis.key}
          legend={`Judgement: ${axis.name}`}
          name={`${id}-${axis.key}`}
          value={judgements[axis.key]}
          emphasis
          options={axis.judgements.map((choice) => ({
            key: choice.key,
            label: choice.label,
            content: <JudgementMark judgement={choice.key} label={choice.label} />,
          }))}
          onChange={(judgement) => {
            onJudge(axis.key, judgement);
          }}
        />
      ))}
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-support`}>Support for the judgement</Label>
        <Textarea
          id={`${id}-support`}
          value={support}
          maxLength={5000}
          rows={2}
          placeholder="Quote or describe what in the report led to it."
          onChange={(event) => {
            onSupport(event.target.value);
          }}
        />
      </div>
    </fieldset>
  );
}

/** One choice from a few, as radio buttons that look like pills. */
function Choices({
  legend,
  name,
  value,
  options,
  onChange,
  emphasis = false,
}: {
  legend: string;
  name: string;
  value: string | undefined;
  options: { key: string; label: string; content?: ReactNode }[];
  onChange: (key: string) => void;
  emphasis?: boolean;
}) {
  return (
    <fieldset className="grid gap-1.5">
      <legend className={cn("mb-1.5 text-sm", emphasis && "font-medium")}>{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <label
            key={option.key}
            className={cn(
              "cursor-pointer rounded-full border border-border px-3 py-1 text-sm",
              "has-checked:border-primary has-checked:bg-primary/10 has-checked:font-medium",
              "has-focus-visible:ring-3 has-focus-visible:ring-ring/50 has-disabled:cursor-default has-disabled:opacity-70",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.key}
              checked={value === option.key}
              onChange={() => {
                onChange(option.key);
              }}
              className="sr-only"
            />
            {option.content ?? option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Other people's assessments of this study, unless blind mode hides them. */
export function OtherAssessments({
  pid,
  rid,
  tool,
  others,
  canChoose,
}: {
  pid: string;
  rid: string;
  tool: RobTool;
  others: Assessment[];
  canChoose: boolean;
}) {
  const choose = useProjectMutation((assessmentId: string) => chooseFinal(pid, rid, assessmentId), {
    invalidate: [robKeys.all(pid)],
    success: "Chosen as the final assessment.",
  });
  if (others.length === 0) return null;
  // By axis: QUADAS-2 calls "low" a low risk on one axis and a low concern on the other.
  const labels = new Map(
    tool.variants.flatMap((variant) =>
      variant.domains.flatMap((domain) =>
        domain.axes.flatMap((axis) =>
          axis.judgements.map((choice) => [`${axis.key}.${choice.key}`, choice.label] as const),
        ),
      ),
    ),
  );
  // "Patient selection", or "Patient selection: applicability" where a domain has two axes.
  const cells = new Map(
    tool.variants.flatMap((variant) =>
      variant.domains.flatMap((d) =>
        d.axes.map(
          (axis) =>
            [
              `${d.key}.${axis.key}`,
              d.axes.length > 1 ? `${d.name}: ${axis.name}` : d.name,
            ] as const,
        ),
      ),
    ),
  );
  return (
    <section aria-label="Everyone's assessments" className="grid gap-3">
      <h3 className="text-base font-medium">Everyone&apos;s assessments</h3>
      <ul className="grid gap-3">
        {others.map((assessment) => (
          <li
            key={assessment.id}
            className="grid gap-2 rounded-xl border border-border bg-card p-4 text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {assessment.mine ? "You" : (assessment.assessor ?? "A former member")}
              </span>
              <Badge variant={assessment.status === "submitted" ? "outline" : "secondary"}>
                {assessment.status === "submitted" ? "Submitted" : "Draft"}
              </Badge>
              {assessment.final && <Badge>Final</Badge>}
              {canChoose && assessment.status === "submitted" && !assessment.final && (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={choose.isPending}
                  onClick={() => {
                    choose.mutate(assessment.id);
                  }}
                >
                  Use as final
                </Button>
              )}
            </div>
            <dl className="grid gap-1 sm:grid-cols-2">
              {Object.entries(assessment.judgements).flatMap(([domain, judged]) =>
                Object.entries(judged).map(([axis, judgement]) => (
                  <div key={`${domain}.${axis}`} className="flex flex-wrap items-center gap-2">
                    <dt className="text-muted-foreground">
                      {cells.get(`${domain}.${axis}`) ?? domain}
                    </dt>
                    <dd>
                      <JudgementMark
                        judgement={judgement}
                        label={labels.get(`${axis}.${judgement}`) ?? judgement}
                      />
                    </dd>
                  </div>
                )),
              )}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}

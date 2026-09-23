import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, CircleHelpIcon, SparklesIcon, XIcon } from "lucide-react";

import { errorMessage } from "@/api/client";
import { askSuggestion, llmKeys, suggestionQuery, type Suggestion } from "@/api/llm";
import type { Stage } from "@/api/screening";
import { Button } from "@/components/ui/button";
import { DECISIONS } from "@/features/screening/wording";

const PROVIDERS: Record<string, string> = {
  anthropic: "Anthropic (Claude)",
  openai_compatible: "the AI service this Winnow instance is set up with",
};

const VERDICTS = {
  met: { label: "met", icon: CheckIcon },
  not_met: { label: "not met", icon: XIcon },
  unclear: { label: "unclear", icon: CircleHelpIcon },
} as const;

/**
 * Guide 8.11: on request, the AI provider's suggestion for this record, with its reading
 * of each criterion and a short rationale. It never decides; the page says where the
 * record goes before anyone asks.
 */
export function SuggestionBox({
  pid,
  rid,
  stage,
  provider,
}: {
  pid: string;
  rid: string;
  stage: Stage;
  provider: string | null | undefined;
}) {
  const queryClient = useQueryClient();
  const { data: suggestion } = useQuery(suggestionQuery(pid, rid, stage));
  const ask = useMutation({
    mutationFn: () => askSuggestion(pid, rid, stage),
    onSuccess: (answer) => {
      queryClient.setQueryData(llmKeys.suggestion(pid, rid, stage), answer);
    },
  });
  const where = PROVIDERS[provider ?? ""] ?? PROVIDERS.openai_compatible;

  return (
    <section aria-labelledby="suggestion-heading" className="grid gap-2">
      <h3
        id="suggestion-heading"
        className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase"
      >
        <SparklesIcon className="size-3.5" aria-hidden="true" /> AI suggestion
      </h3>
      <p className="text-xs text-muted-foreground">
        Asking sends this record&apos;s title, abstract and keywords, and the review&apos;s
        criteria, to {where}. It is advice: it never decides for you.
      </p>
      {suggestion && <Answer suggestion={suggestion} />}
      {ask.isError && (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(ask.error)}
        </p>
      )}
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={ask.isPending}
          onClick={() => {
            ask.mutate();
          }}
        >
          <SparklesIcon aria-hidden="true" />
          {ask.isPending ? "Asking…" : suggestion ? "Ask again" : "Ask for a suggestion"}
        </Button>
      </div>
    </section>
  );
}

function Answer({ suggestion }: { suggestion: Suggestion }) {
  const decision = DECISIONS.find((option) => option.value === suggestion.decision);
  return (
    <div className="grid gap-2 rounded-md border bg-card p-3 text-sm">
      <p className="flex flex-wrap items-center gap-1.5">
        {decision && <decision.icon className="size-4" aria-hidden="true" />}
        <span>
          Suggests <strong>{decision?.label ?? suggestion.decision}</strong>,{" "}
          {Math.round(suggestion.confidence * 100)}% sure
        </span>
      </p>
      {suggestion.criteria.length > 0 && (
        <ul aria-label="Criteria" className="grid gap-1">
          {suggestion.criteria.map((item) => {
            const verdict = VERDICTS[item.verdict];
            return (
              <li key={item.criterion_id} className="flex items-start gap-1.5 text-xs">
                <verdict.icon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                <span>
                  <span className="font-medium">{verdict.label}:</span> {item.text}
                  <span className="text-muted-foreground">
                    {" "}
                    ({item.kind === "inclusion" ? "inclusion" : "exclusion"})
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-sm">{suggestion.rationale}</p>
      <p className="text-xs text-muted-foreground">
        {suggestion.model}, {new Date(suggestion.created_at).toLocaleString()}
      </p>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { CopyIcon, RotateCcwIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { methodsQuery, type Methods } from "@/api/reporting";
import { FormAlert } from "@/components/forms/FormAlert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

/** Guide 8.15: the methods paragraph, with the review's real numbers, to edit and copy. */
export function MethodsView({ pid }: { pid: string }) {
  const { data, error, isPending } = useQuery(methodsQuery(pid));
  if (isPending) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;
  // Written afresh whenever Winnow's own text changes; edits stay until then.
  return <Editor key={data.text} methods={data} />;
}

function Editor({ methods }: { methods: Methods }) {
  const id = useId();
  const [text, setText] = useState(methods.text);

  if (!methods.text) {
    return (
      <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
        Nothing to describe yet. The text appears once records are imported and screened.
      </p>
    );
  }
  return (
    <div className="grid gap-4">
      {!methods.complete && (
        <FormAlert tone="warning">
          Screening is not finished, so these numbers are a snapshot. Come back when it is.
        </FormAlert>
      )}
      {methods.blind && (
        <p className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
          Blind mode is on, so sentences about agreement between reviewers and how disagreements
          were settled are left out for you.
        </p>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-text`}>Methods text</Label>
        <Textarea
          id={`${id}-text`}
          value={text}
          rows={12}
          aria-describedby={`${id}-hint`}
          className="text-base leading-relaxed"
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          Edit freely before copying; changes are not saved. Check it against your protocol: it
          states only what Winnow recorded.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() => {
            navigator.clipboard.writeText(text).then(
              () => toast.success("Copied."),
              () => toast.error("Could not copy. Select the text and copy it yourself."),
            );
          }}
        >
          <CopyIcon aria-hidden="true" /> Copy
        </Button>
        <Button
          variant="outline"
          disabled={text === methods.text}
          onClick={() => {
            setText(methods.text);
          }}
        >
          <RotateCcwIcon aria-hidden="true" /> Back to Winnow&apos;s text
        </Button>
      </div>
    </div>
  );
}

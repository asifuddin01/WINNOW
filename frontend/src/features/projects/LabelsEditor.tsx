import { useQuery } from "@tanstack/react-query";
import { TrashIcon } from "lucide-react";
import { useState } from "react";

import { addLabel, deleteLabel, labelsQuery, projectKeys, type Color } from "@/api/projects";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/ui/button";
import { ColorChoice } from "@/features/projects/ColorChoice";
import { COLOR_CHIP, COLOR_DOT, COLOR_NAMES } from "@/features/projects/palette";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { cn } from "@/lib/utils";

/** Coloured tags reviewers can put on records and filter by (guide 8.9). */
export function LabelsEditor({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const { data: labels = [] } = useQuery(labelsQuery(pid));
  const invalidate = [projectKeys.labels(pid)];
  const add = useProjectMutation(
    (values: { name: string; color: Color }) => addLabel(pid, values),
    {
      invalidate,
    },
  );
  const remove = useProjectMutation((id: string) => deleteLabel(pid, id), {
    invalidate,
    success: "Label deleted.",
  });
  const [name, setName] = useState("");
  const [color, setColor] = useState<Color>("blue");

  return (
    <div className="grid gap-4">
      {labels.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No labels yet. Labels are free-form tags, such as “key paper” or “check with Sara”.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {labels.map((label) => (
            <li
              key={label.id}
              className={cn(
                "flex items-center gap-2 rounded-full border px-3 py-1 text-sm",
                COLOR_CHIP[label.color],
              )}
            >
              <span
                className={cn("size-2 rounded-full", COLOR_DOT[label.color])}
                aria-hidden="true"
              />
              {label.name}
              <span className="sr-only">({COLOR_NAMES[label.color]})</span>
              {canEdit && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="-mr-2 size-6 hover:text-destructive"
                  aria-label={`Delete label “${label.name}”`}
                  onClick={() => {
                    remove.mutate(label.id);
                  }}
                >
                  <TrashIcon aria-hidden="true" className="size-3.5" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="grid gap-3 rounded-lg border border-dashed border-input p-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim()) return;
            add.mutate({ name: name.trim(), color });
            setName("");
          }}
        >
          <TextField
            label="New label"
            placeholder="Key paper"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          <ColorChoice value={color} onChange={setColor} />
          <Button
            type="submit"
            variant="outline"
            className="justify-self-start"
            disabled={add.isPending}
          >
            Add label
          </Button>
        </form>
      )}
    </div>
  );
}

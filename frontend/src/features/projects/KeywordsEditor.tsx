import { useQuery } from "@tanstack/react-query";
import { TrashIcon, XIcon } from "lucide-react";
import { useState } from "react";

import {
  addKeywordGroup,
  addKeywords,
  deleteKeyword,
  deleteKeywordGroup,
  keywordGroupsQuery,
  projectKeys,
  type Color,
  type KeywordGroup,
  type KeywordKind,
} from "@/api/projects";
import { SelectField } from "@/components/forms/SelectField";
import { TextField } from "@/components/forms/TextField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ColorChoice } from "@/features/projects/ColorChoice";
import { COLOR_CHIP, COLOR_DOT, COLOR_NAMES } from "@/features/projects/palette";
import { splitTerms } from "@/features/projects/schemas";
import { useProjectMutation } from "@/features/projects/use-project-mutation";
import { KEYWORD_KINDS } from "@/features/projects/wording";
import { cn } from "@/lib/utils";

const KIND_OPTIONS = Object.entries(KEYWORD_KINDS).map(([value, label]) => ({
  value: value as KeywordKind,
  label,
}));

/** Keyword groups are highlighted while screening, each in its own colour (guide 8.5). */
export function KeywordsEditor({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const { data: groups = [] } = useQuery(keywordGroupsQuery(pid));
  const invalidate = [projectKeys.keywords(pid)];
  const addGroup = useProjectMutation(
    (values: { name: string; kind: KeywordKind; color: Color }) => addKeywordGroup(pid, values),
    { invalidate },
  );
  const removeGroup = useProjectMutation((id: string) => deleteKeywordGroup(pid, id), {
    invalidate,
    success: "Keyword group deleted.",
  });

  return (
    <div className="grid gap-4">
      {groups.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No keyword groups yet. A group is a set of terms that mean the same thing, such as
          “nurses, nursing staff, RN”.
        </p>
      )}
      <ul className="grid gap-4">
        {groups.map((group) => (
          <li key={group.id}>
            <GroupCard
              pid={pid}
              group={group}
              canEdit={canEdit}
              onDelete={() => {
                removeGroup.mutate(group.id);
              }}
            />
          </li>
        ))}
      </ul>
      {canEdit && (
        <AddGroup
          pending={addGroup.isPending}
          onAdd={(values) => {
            addGroup.mutate(values);
          }}
        />
      )}
    </div>
  );
}

function GroupCard({
  pid,
  group,
  canEdit,
  onDelete,
}: {
  pid: string;
  group: KeywordGroup;
  canEdit: boolean;
  onDelete: () => void;
}) {
  const invalidate = [projectKeys.keywords(pid)];
  const add = useProjectMutation(
    (body: { terms: string[]; is_regex: boolean; whole_word: boolean }) =>
      addKeywords(pid, { group_id: group.id, ...body }),
    { invalidate },
  );
  const remove = useProjectMutation((id: string) => deleteKeyword(pid, id), { invalidate });
  const [terms, setTerms] = useState("");
  const [isRegex, setIsRegex] = useState(false);
  const [wholeWord, setWholeWord] = useState(true);

  return (
    <section
      aria-labelledby={`group-${group.id}`}
      className="grid gap-3 rounded-xl border border-border bg-card p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("size-3 rounded-full", COLOR_DOT[group.color])} aria-hidden="true" />
        <h3 id={`group-${group.id}`} className="text-sm font-semibold">
          {group.name}
        </h3>
        <span className="sr-only">({COLOR_NAMES[group.color]})</span>
        <Badge variant="outline">{KEYWORD_KINDS[group.kind]}</Badge>
        {canEdit && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto text-muted-foreground hover:text-destructive"
            aria-label={`Delete group ${group.name}`}
            onClick={onDelete}
          >
            <TrashIcon aria-hidden="true" /> Delete group
          </Button>
        )}
      </div>
      {group.keywords.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {group.keywords.map((keyword) => (
            <li
              key={keyword.id}
              className={cn(
                "flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm",
                COLOR_CHIP[group.color],
              )}
            >
              <span className={keyword.is_regex ? "font-mono text-xs" : undefined}>
                {keyword.term}
              </span>
              {canEdit && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="-mr-1.5 size-5 hover:text-destructive"
                  aria-label={`Remove “${keyword.term}” from ${group.name}`}
                  onClick={() => {
                    remove.mutate(keyword.id);
                  }}
                >
                  <XIcon aria-hidden="true" className="size-3" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="grid gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const list = splitTerms(terms);
            if (list.length === 0) return;
            add.mutate({ terms: list, is_regex: isRegex, whole_word: wholeWord });
            setTerms("");
          }}
        >
          <Textarea
            aria-label={`Terms for ${group.name}`}
            placeholder="nurses, nursing staff, RN"
            rows={2}
            value={terms}
            onChange={(event) => {
              setTerms(event.target.value);
            }}
          />
          <p className="text-xs text-muted-foreground">
            One per line, or separated by commas.
            {isRegex && " Patterns use a safe subset: no lookarounds or nested repeats."}
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <span className="flex items-center gap-2">
              <Checkbox
                id={`whole-${group.id}`}
                checked={wholeWord}
                onCheckedChange={(checked) => {
                  setWholeWord(checked === true);
                }}
              />
              <Label htmlFor={`whole-${group.id}`}>Whole words only</Label>
            </span>
            <span className="flex items-center gap-2">
              <Checkbox
                id={`regex-${group.id}`}
                checked={isRegex}
                onCheckedChange={(checked) => {
                  setIsRegex(checked === true);
                }}
              />
              <Label htmlFor={`regex-${group.id}`}>These are patterns</Label>
            </span>
            <Button type="submit" size="sm" variant="outline" disabled={add.isPending}>
              Add to {group.name}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

function AddGroup({
  pending,
  onAdd,
}: {
  pending: boolean;
  onAdd: (values: { name: string; kind: KeywordKind; color: Color }) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<KeywordKind>("include");
  const [color, setColor] = useState<Color>("amber");

  return (
    <form
      className="grid gap-3 rounded-lg border border-dashed border-input p-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        onAdd({ name: name.trim(), kind, color });
        setName("");
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label="New keyword group"
          placeholder="Population"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <SelectField label="What it means" value={kind} options={KIND_OPTIONS} onChange={setKind} />
      </div>
      <ColorChoice value={color} onChange={setColor} label="Highlight colour" />
      <Button type="submit" variant="outline" className="justify-self-start" disabled={pending}>
        Add group
      </Button>
    </form>
  );
}

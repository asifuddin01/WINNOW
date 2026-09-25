import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { DownloadIcon, EyeOffIcon } from "lucide-react";
import { useId, useState } from "react";

import { errorMessage } from "@/api/client";
import { membersQuery } from "@/api/projects";
import { auditCsvUrl, auditQuery, type AuditEntry, type AuditFilters } from "@/api/reporting";
import { FormAlert } from "@/components/forms/FormAlert";
import { SelectField } from "@/components/forms/SelectField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { describe } from "@/features/report/audit-words";
import { timeAgo } from "@/lib/format";

const ALL = "all";

/** Filtering by a family ("decision") matches every action in it (guide 12.8). */
const FAMILIES = [
  { value: ALL, label: "Everything" },
  { value: "decision", label: "Screening decisions" },
  { value: "conflict", label: "Conflicts" },
  { value: "import", label: "Imports" },
  { value: "dedup", label: "Duplicates" },
  { value: "fulltext", label: "Full texts" },
  { value: "rob", label: "Risk of bias" },
  { value: "llm", label: "AI suggestions" },
  { value: "setup", label: "Criteria, keywords, reasons and labels" },
  { value: "member", label: "Team" },
  { value: "project", label: "Review and settings" },
  { value: "prisma", label: "PRISMA counts" },
  { value: "export", label: "Exports" },
];

export function AuditView({ pid }: { pid: string }) {
  const id = useId();
  const { data: members } = useQuery(membersQuery(pid));
  const [family, setFamily] = useState(ALL);
  const [person, setPerson] = useState(ALL);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const filters: AuditFilters = {
    action: family === ALL ? undefined : family,
    user_id: person === ALL ? undefined : person,
    since: since || undefined,
    until: until || undefined,
  };
  const { data, error, isPending, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useInfiniteQuery(auditQuery(pid, filters));
  const entries = data?.pages.flatMap((page) => page.items) ?? [];

  const people = [
    { value: ALL, label: "Anyone" },
    ...(members?.items ?? []).map((member) => ({ value: member.user.id, label: member.user.name })),
  ];

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 rounded-xl border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-4">
        <SelectField label="What" value={family} options={FAMILIES} onChange={setFamily} />
        <SelectField label="Who" value={person} options={people} onChange={setPerson} />
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-since`}>From</Label>
          <Input
            id={`${id}-since`}
            type="date"
            value={since}
            max={until || undefined}
            onChange={(event) => {
              setSince(event.target.value);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-until`}>To</Label>
          <Input
            id={`${id}-until`}
            type="date"
            value={until}
            min={since || undefined}
            onChange={(event) => {
              setUntil(event.target.value);
            }}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Every change to the review, newest first. Nothing here can be edited or deleted.
        </p>
        <Button asChild variant="outline" size="sm">
          <a href={auditCsvUrl(pid, filters)} download>
            <DownloadIcon aria-hidden="true" /> Download as CSV
          </a>
        </Button>
      </div>

      {isPending ? (
        <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />
      ) : error ? (
        <FormAlert>{errorMessage(error)}</FormAlert>
      ) : entries.length === 0 ? (
        <p className="rounded-xl border border-dashed border-input p-6 text-center text-sm text-muted-foreground">
          Nothing matches these filters.
        </p>
      ) : (
        <ol className="grid divide-y divide-border rounded-xl border border-border bg-card">
          {entries.map((entry) => (
            <li key={entry.id}>
              <Entry entry={entry} />
            </li>
          ))}
        </ol>
      )}
      {hasNextPage && (
        <div>
          <Button
            variant="outline"
            disabled={isFetchingNextPage}
            onClick={() => {
              void fetchNextPage();
            }}
          >
            {isFetchingNextPage ? "Loading…" : "Show older"}
          </Button>
        </div>
      )}
    </div>
  );
}

function Entry({ entry }: { entry: AuditEntry }) {
  const changes = entry.before ?? entry.after;
  return (
    <div className="grid gap-1 px-4 py-3 text-sm">
      <p>
        <span className="font-medium">{entry.actor ?? "Winnow"}</span> {describe(entry.action)}
      </p>
      <p className="text-xs text-muted-foreground">
        <time dateTime={entry.at} title={new Date(entry.at).toLocaleString()}>
          {timeAgo(entry.at)}
        </time>
        {" · "}
        <code>{entry.action}</code>
        {entry.ip && ` · ${entry.ip}`}
      </p>
      {entry.withheld ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <EyeOffIcon className="size-3.5" aria-hidden="true" />
          What was decided is hidden while you are blind to others&apos; decisions.
        </p>
      ) : (
        changes && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">Details</summary>
            <dl className="mt-1 grid gap-1">
              {entry.before && <Change label="Before" value={entry.before} />}
              {entry.after && <Change label="After" value={entry.after} />}
            </dl>
          </details>
        )
      )}
    </div>
  );
}

function Change({ label, value }: { label: string; value: Record<string, unknown> }) {
  return (
    <div>
      <dt className="font-medium">{label}</dt>
      <dd>
        <pre className="overflow-x-auto rounded-md bg-muted p-2 whitespace-pre-wrap break-all">
          {JSON.stringify(value, null, 2)}
        </pre>
      </dd>
    </div>
  );
}

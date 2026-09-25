import { CheckIcon, SplitIcon } from "lucide-react";
import { useState } from "react";

import type { Cluster, ClusterMember } from "@/api/dedup";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ROWS = ["title", "authors", "year", "journal", "volume", "issue", "pages", "doi", "pmid"];

/**
 * Which fields the copies disagree about; those are the ones worth reading. Case,
 * punctuation and spacing do not count — every database writes titles its own way, and
 * marking "Deep learning" against "Deep Learning" would hide the year that really differs.
 */
function differences(members: ClusterMember[]): Set<string> {
  const differing = new Set<string>();
  for (const field of ROWS) {
    const values = members.map((member) => comparable(value(member, field)));
    if (new Set(values).size > 1) differing.add(field);
  }
  return differing;
}

function comparable(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function value(member: ClusterMember, field: string): string {
  const raw = member[field as keyof ClusterMember];
  if (Array.isArray(raw)) return raw.join("; ");
  return raw == null ? "" : String(raw);
}

const LABELS: Record<string, string> = {
  title: "Title",
  authors: "Authors",
  year: "Year",
  journal: "Journal",
  volume: "Volume",
  issue: "Issue",
  pages: "Pages",
  doi: "DOI",
  pmid: "PubMed id",
};

/**
 * One group of records that look like the same work, side by side (guide 8.4). The
 * differences are marked, because they are what decides it: two DOIs that disagree are
 * usually an erratum or a conference abstract, not a duplicate.
 */
export function ClusterCard({
  cluster,
  canDecide,
  busy,
  onMerge,
  onIgnore,
}: {
  cluster: Cluster;
  canDecide: boolean;
  busy: boolean;
  onMerge: (primaryId: string) => void;
  onIgnore: () => void;
}) {
  const suggested = cluster.members.find((member) => member.is_primary) ?? cluster.members[0];
  const [primaryId, setPrimaryId] = useState(suggested?.id ?? "");
  const differing = differences(cluster.members);
  const [showAbstract, setShowAbstract] = useState(false);

  return (
    <article
      aria-label={`Possible duplicate: ${suggested?.title ?? "untitled"}`}
      className="grid gap-4 rounded-xl border border-border bg-card p-4"
    >
      <header className="flex flex-wrap items-center gap-2">
        <Badge variant={cluster.auto_resolvable ? "secondary" : "outline"}>
          {cluster.auto_resolvable ? "Certain" : `${Math.round(cluster.score * 100)}% alike`}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {cluster.members.length} copies · they differ on{" "}
          {[...differing].map((field) => LABELS[field]?.toLowerCase()).join(", ") ||
            "nothing Winnow compares"}
        </span>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] border-collapse text-sm">
          <caption className="sr-only">
            The records in this group, one column each, with the fields they disagree about
          </caption>
          <thead>
            <tr>
              <th scope="col" className="w-28 p-2 text-left font-medium text-muted-foreground">
                Field
              </th>
              {cluster.members.map((member) => (
                <th key={member.id} scope="col" className="p-2 text-left">
                  <label className="flex cursor-pointer items-start gap-2">
                    <input
                      type="radio"
                      id={`keep-${cluster.id}-${member.id}`}
                      name={`primary-${cluster.id}`}
                      className="mt-1"
                      checked={primaryId === member.id}
                      disabled={!canDecide}
                      aria-label={`Keep the copy from ${
                        member.database_name ?? member.source ?? "this import"
                      }`}
                      onChange={() => {
                        setPrimaryId(member.id);
                      }}
                    />
                    <span>
                      <span className="block text-xs font-medium">
                        Keep this one
                        {member.id === suggested?.id && (
                          <span className="font-normal text-muted-foreground">
                            {" "}
                            · Winnow suggests it
                          </span>
                        )}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {member.database_name ?? member.source ?? "Imported"}
                      </span>
                    </span>
                  </label>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.filter((field) => cluster.members.some((member) => value(member, field))).map(
              (field) => (
                <tr key={field} className="border-t border-border/60 align-top">
                  <th scope="row" className="p-2 text-left font-medium text-muted-foreground">
                    {LABELS[field]}
                  </th>
                  {cluster.members.map((member) => (
                    <td
                      key={member.id}
                      className={cn(
                        "p-2",
                        differing.has(field) && "bg-maybe/10 font-medium",
                        field === "doi" || field === "pmid" ? "font-mono text-xs" : "",
                      )}
                    >
                      {value(member, field) || "—"}
                      {differing.has(field) && <span className="sr-only"> (differs)</span>}
                    </td>
                  ))}
                </tr>
              ),
            )}
            {showAbstract && (
              <tr className="border-t border-border/60 align-top">
                <th scope="row" className="p-2 text-left font-medium text-muted-foreground">
                  Abstract
                </th>
                {cluster.members.map((member) => (
                  <td key={member.id} className="max-w-md p-2 text-xs">
                    {member.abstract ?? "—"}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {canDecide && (
          <>
            <Button
              size="sm"
              disabled={busy || !primaryId}
              onClick={() => {
                onMerge(primaryId);
              }}
            >
              <CheckIcon aria-hidden="true" /> Merge, keeping the chosen copy
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={onIgnore}>
              <SplitIcon aria-hidden="true" /> Not duplicates
            </Button>
          </>
        )}
        <Button
          size="sm"
          variant="ghost"
          aria-expanded={showAbstract}
          onClick={() => {
            setShowAbstract((current) => !current);
          }}
        >
          {showAbstract ? "Hide abstracts" : "Compare abstracts"}
        </Button>
      </div>
    </article>
  );
}

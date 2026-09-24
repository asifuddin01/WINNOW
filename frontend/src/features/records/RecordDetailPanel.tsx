import { useQuery } from "@tanstack/react-query";

import { recordQuery } from "@/api/records";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

/** One record, beside the table: everything the import kept. */
export function RecordDetailPanel({ pid, rid }: { pid: string; rid: string }) {
  const { data: record, isPending } = useQuery(recordQuery(pid, rid));
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" />;
  if (!record) return null;

  const citation = [
    record.authors.join("; "),
    record.year,
    record.journal,
    record.volume && `${record.volume}${record.issue ? `(${record.issue})` : ""}`,
    record.pages,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <article
      aria-labelledby="record-title"
      className="grid gap-4 rounded-xl border border-border bg-card p-5"
    >
      <div>
        <h2 id="record-title" className="text-base font-semibold">
          {record.title ?? "(no title)"}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{citation}</p>
      </div>

      {record.relevance_score !== null && (
        <div>
          <p className="text-sm">Relevance {Math.round(record.relevance_score * 100)}%</p>
          <p className="mt-1 text-xs text-muted-foreground">
            The ranking model's estimate from this review's decisions.
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2 text-xs">
        {record.doi && (
          <a
            href={`https://doi.org/${record.doi}`}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-full border border-border px-2.5 py-1 font-mono hover:border-ring"
          >
            {record.doi}
          </a>
        )}
        {record.pmid && (
          <a
            href={`https://pubmed.ncbi.nlm.nih.gov/${record.pmid}/`}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-full border border-border px-2.5 py-1 hover:border-ring"
          >
            PMID {record.pmid}
          </a>
        )}
        {record.url && (
          <a
            href={record.url}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-full border border-border px-2.5 py-1 hover:border-ring"
          >
            Publisher
          </a>
        )}
      </div>

      {record.abstract ? (
        <div className="max-w-[75ch] text-[17px] leading-relaxed whitespace-pre-line">
          {record.abstract}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">This record came in without an abstract.</p>
      )}

      {record.keywords.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {record.keywords.slice(0, 30).map((keyword) => (
            <li key={keyword} className="rounded-full bg-muted px-2.5 py-0.5 text-xs">
              {keyword}
            </li>
          ))}
        </ul>
      )}

      <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-[8rem_1fr]">
        {record.publication_type.length > 0 && (
          <>
            <dt>Type</dt>
            <dd>{record.publication_type.join(", ")}</dd>
          </>
        )}
        {record.language && (
          <>
            <dt>Language</dt>
            <dd>{record.language}</dd>
          </>
        )}
        {record.source && (
          <>
            <dt>Imported from</dt>
            <dd>{record.source}</dd>
          </>
        )}
      </dl>

      {record.is_duplicate && <Badge variant="outline">Merged as a duplicate</Badge>}
    </article>
  );
}

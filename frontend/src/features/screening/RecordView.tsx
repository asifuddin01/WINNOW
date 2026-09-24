import { ExternalLinkIcon } from "lucide-react";
import { useMemo } from "react";

import type { ScreeningItem } from "@/api/screening";
import { Badge } from "@/components/ui/badge";
import { COLOR_CHIP } from "@/features/projects/palette";
import { highlight, type Matcher } from "@/features/screening/highlight";
import { cn } from "@/lib/utils";

function Highlighted({ text, matchers }: { text: string; matchers: Matcher[] }) {
  const segments = useMemo(() => highlight(text, matchers), [text, matchers]);
  return (
    <>
      {segments.map((segment, index) =>
        segment.color ? (
          <mark
            key={index}
            title={segment.name}
            className={cn("rounded-sm border px-0.5 text-inherit", COLOR_CHIP[segment.color])}
          >
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * One record for screening (guide 8.5): title large, then the citation, links that open
 * in a new tab, and the abstract at reading size — 17-18 px, 1.6 line height, 75ch wide.
 */
export function RecordView({
  item,
  matchers,
  focus = false,
  showScore = false,
  compact = false,
}: {
  item: ScreeningItem;
  matchers: Matcher[];
  focus?: boolean;
  showScore?: boolean;
  /** At full text the PDF is what is read: the abstract folds away. */
  compact?: boolean;
}) {
  const citation = [
    item.journal,
    item.year,
    item.volume && `${item.volume}${item.issue ? `(${item.issue})` : ""}`,
    item.pages,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <article aria-labelledby={`record-${item.id}`} className="grid gap-4">
      <header className="grid gap-2">
        <h2
          id={`record-${item.id}`}
          className={cn(
            "font-semibold tracking-tight text-balance",
            focus ? "text-2xl md:text-3xl" : "text-xl md:text-2xl",
          )}
        >
          {item.title ? <Highlighted text={item.title} matchers={matchers} /> : "(no title)"}
        </h2>
        {item.authors.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {item.authors.slice(0, 12).join("; ")}
            {item.authors.length > 12 ? ` and ${item.authors.length - 12} more` : ""}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {citation && <span className="text-muted-foreground">{citation}</span>}
          {item.doi && (
            <a
              href={`https://doi.org/${item.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 font-mono text-xs hover:border-ring"
            >
              DOI {item.doi} <ExternalLinkIcon className="size-3" aria-hidden="true" />
            </a>
          )}
          {item.pmid && (
            <a
              href={`https://pubmed.ncbi.nlm.nih.gov/${item.pmid}/`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs hover:border-ring"
            >
              PMID {item.pmid} <ExternalLinkIcon className="size-3" aria-hidden="true" />
            </a>
          )}
          {showScore && item.relevance_score != null && (
            <Badge variant="secondary">Relevance {Math.round(item.relevance_score * 100)}%</Badge>
          )}
        </div>
      </header>

      {item.abstract && compact ? (
        <details className="group max-w-[75ch]">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground select-none">
            Abstract
          </summary>
          <div className="mt-2 leading-relaxed whitespace-pre-line">
            <Highlighted text={item.abstract} matchers={matchers} />
          </div>
        </details>
      ) : item.abstract ? (
        <div
          className={cn(
            "max-w-[75ch] leading-relaxed whitespace-pre-line",
            focus ? "text-[19px] md:text-xl" : "text-[17px] md:text-lg",
          )}
        >
          <Highlighted text={item.abstract} matchers={matchers} />
        </div>
      ) : compact ? null : (
        <p className="text-sm text-muted-foreground">This record came in without an abstract.</p>
      )}

      {!compact && (item.keywords.length > 0 || item.publication_type.length > 0) && (
        <dl className="grid gap-1 text-sm">
          {item.keywords.length > 0 && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-muted-foreground">Keywords</dt>
              <dd>
                <Highlighted text={item.keywords.slice(0, 30).join("; ")} matchers={matchers} />
              </dd>
            </div>
          )}
          {item.publication_type.length > 0 && (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-muted-foreground">Type</dt>
              <dd>{item.publication_type.join(", ")}</dd>
            </div>
          )}
        </dl>
      )}
    </article>
  );
}

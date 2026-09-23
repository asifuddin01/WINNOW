/**
 * Where a search can come from (guide 8.3, PRISMA-S). Bibliographic databases first,
 * then preprint servers and trial registers, because a scoping review usually needs both.
 */
export const DATABASES = [
  "PubMed",
  "Embase",
  "Scopus",
  "Web of Science",
  "IEEE Xplore",
  "ACM Digital Library",
  "CINAHL",
  "Cochrane Library",
  "PsycINFO",
  "ProQuest",
  "Google Scholar",
  "Semantic Scholar",
  "Dimensions",
  "arXiv",
  "bioRxiv",
  "medRxiv",
  "SSRN",
  "ClinicalTrials.gov",
  "WHO ICTRP",
  "Hand search",
  "Other",
] as const;

export type Database = (typeof DATABASES)[number];

export const DATABASE_OPTIONS = DATABASES.map((name) => ({ value: name, label: name }));

/** What each export tends to be called, so a drop of twenty files names itself. */
const BY_FILENAME: [RegExp, Database][] = [
  [/ieee/i, "IEEE Xplore"],
  [/acm|dl\.acm/i, "ACM Digital Library"],
  [/scopus/i, "Scopus"],
  [/pubmed|medline|nbib|pmc/i, "PubMed"],
  [/embase|ovid/i, "Embase"],
  [/wos|web.?of.?science|savedrecs/i, "Web of Science"],
  [/cinahl|ebsco/i, "CINAHL"],
  [/cochrane|central/i, "Cochrane Library"],
  [/psycinfo|psychinfo/i, "PsycINFO"],
  [/proquest/i, "ProQuest"],
  [/scholar/i, "Google Scholar"],
  [/semantic/i, "Semantic Scholar"],
  [/dimensions/i, "Dimensions"],
  [/arxiv/i, "arXiv"],
  [/biorxiv/i, "bioRxiv"],
  [/medrxiv/i, "medRxiv"],
  [/ssrn/i, "SSRN"],
  [/clinicaltrials|ctgov/i, "ClinicalTrials.gov"],
  [/ictrp/i, "WHO ICTRP"],
];

/** A guess from the file's own name; "Other" when nothing matches, never wrong silently. */
export function databaseFor(filename: string, fallback = "Other"): string {
  for (const [pattern, name] of BY_FILENAME) {
    if (pattern.test(filename)) return name;
  }
  return fallback;
}

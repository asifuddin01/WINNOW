# Using Winnow

Winnow takes a systematic, scoping or rapid review from search results to a PRISMA
diagram. Its stages are:

1. Import the searches and remove duplicates.
2. Screen titles and abstracts, then full texts, with two or more reviewers working
   independently.
3. Resolve disagreements.
4. Extract data and assess risk of bias.
5. Report.

This guide follows that order. Anywhere in Winnow, **Ctrl+K** (⌘K on a Mac) jumps to
any page, review, record or action.

## Your account

- **Signing up.** Sign up with your email address, or with Google if your instance offers
  it. Confirm your address from the email Winnow sends; until you do, you can't join
  reviews.
- **Account and security** (the menu at the top right):
  - Two-factor sign-in with an authenticator app, plus recovery codes. Keep them
    somewhere safe.
  - Where you are signed in: end any session you don't recognise.
  - Your ORCID iD, if your instance offers ORCID. Once linked, **Continue with ORCID**
    signs you in. ORCID shares no email address, so it only works for an account that
    has linked its iD.
  - Your notification digest (see [Notifications](#notifications)).
- **Colour theme.** Light, dark, or follow your system, from the sun and moon icon.

## Starting a review

**New review** asks three things:

1. **Basics.** The title, the review type, the question and PICO.
2. **Criteria.** Inclusion and exclusion criteria, and keywords to highlight while
   screening.
3. **The team.** Who works on the review.

None of this is final; all of it lives under **Settings** afterwards.

### The team and roles

| Role | Can |
| --- | --- |
| Owner | Everything, including deleting the review or handing it on |
| Admin | Run the review: setup, imports, the team and settings |
| Reviewer | Screen records and read the review |
| Viewer | Read the review and export; change nothing |

**Inviting people.** Invite by email under **Settings → Team**. Someone who already has
an account also sees the invitation in their notifications. You can say who resolves
conflicts, and which stages each person screens.

### Screening settings

**Settings → Screening** holds:

- **Reviewers per record.** How many people must decide each record before it is
  settled. Two is the systematic-review norm.
- **Blind mode.** Reviewers don't see each other's decisions until a record is settled.
- **Maybe.** Whether a "maybe" counts as an include at title and abstract.
- **Assignment.** Everyone screens every record, or the records are split between
  reviewers.
- **Exclusion reasons.** Whether a reason is required to exclude. The reasons themselves
  are edited under **Settings → Exclusion reasons**.
- **Ranking.** Screening by relevance (see below), and when to suggest stopping.

## Importing searches

**Import** accepts these search exports:

| Format | Typical source |
| --- | --- |
| RIS | Most databases and reference managers |
| PubMed MEDLINE (`.nbib`) and PubMed XML | PubMed |
| BibTeX | Reference managers |
| EndNote XML | EndNote |
| Zotero RDF | Zotero, with everything its library holds |
| CSV | You say which column is which |

**Adding files.** Drop up to 20 files at once. Each becomes a separate import you
preview before confirming, with its database, search date and search string. Those go
into the PRISMA diagram and the methods text.

**Progress and undo.** Large imports run in the background, with live progress. An
import can be undone from **Import**, which takes its records out again.

### Duplicates

Deduplication runs on its own after each import:

- **Certain duplicates** (the same DOI or PubMed id, or near-identical metadata) are
  merged automatically. Turn that off in settings if you'd rather decide every one.
- **The rest** are grouped under **Duplicates**, side by side, with the fields that
  differ marked. Merge a group keeping the copy you choose, or mark it "not
  duplicates".
- **Nothing is lost.** Merged copies keep their provenance, and any decisions or notes
  on them move to the record kept.

## Screening

**Screen** shows one record at a time: title, abstract, keywords highlighted, and your
decision panel. The next record is always ready, so you never wait between decisions.

| Key | Does |
| --- | --- |
| I / E / M | Include / exclude / maybe |
| R, then 1–9 | Open the exclusion reasons; choose them by number |
| J or → / K or ← | Next / previous record |
| L | Labels |
| N | A note (write @ and a teammate's name to tell them) |
| H | Keyword highlighting on or off |
| F | Focus mode: the record and the decision, nothing else |
| / | Search within the records to screen |
| ? | All shortcuts |
| Ctrl+Z (⌘Z) | Undo the last decision |

**Screening order.** By default, records come in relevance order. Once you have made
enough decisions, a model learns from them (at least five includes and five excludes).
It then puts the most likely includes first, and retrains as you go. One record in
twenty still comes at random, so the model keeps learning. The overview shows how many
relevant records are probably left, and suggests when stopping is reasonable.

**Full text.** Records included at title and abstract move to **Full text**, where
their PDFs are attached:

- one at a time;
- as a ZIP matched to records;
- or found automatically in open-access sources (Unpaywall, PubMed Central).

When the instance runs ClamAV, every PDF is virus-scanned before anyone opens it. A PDF nobody can obtain is marked
"not retrievable", and PRISMA counts it that way.

**AI suggestions.** Some instances show AI screening suggestions. They are only ever
suggestions, and your decision is what counts.

**Who is screening.** The overview and the screening pages show who else is screening
right now, and which stage. They never show which record, or what anyone decided.

## Conflicts

When reviewers disagree, the record goes to **Conflicts**. Only people allowed to
resolve conflicts see it there, with each reviewer's decision and reasons side by side.
They choose the final decision, which settles the record for everyone.

## Records

**Records** lists every record in the review with its status. It pages quickly through
any number of records, filters by status or import, and sorts by date added, title, year
or relevance. Owners and admins can decide every record a search finds at once, a bulk
decision the audit log records; records already settled are left alone.

The search box understands:

| Search | Finds |
| --- | --- |
| `sleep nurses` | both words, anywhere |
| `"night shift"` | the exact phrase |
| `-melatonin` | records without the word |
| `author:okafor`, `journal:lancet`, `keyword:fatigue` | in that field |
| `year:2015..2024`, `year:2015..` | a range of years |
| `label:rct`, `type:review` | a label, or a publication type |
| a DOI or a PubMed id | that record |

## Data extraction

**Extraction → Forms** builds a form:

- **Field types:** short or long text, numbers with units, single or multiple choice,
  yes/no/unclear, dates, section headings, and tables (one row per arm or outcome).
- **Versions:** publishing a version locks it. Changes go into a new version, and
  extractions keep the version they used.
- **Dual extraction:** a form can ask for two extractors per study.

**Extraction** lists the included studies to extract. With dual extraction, **Consensus**
shows the values the two gave differently, and one of them settles each.

## Risk of bias

**Risk of bias** assesses each included study with RoB 2, ROBINS-I, the Newcastle–Ottawa
Scale or QUADAS-2: a judgement and a reason per domain. **Summary** draws the
traffic-light and summary plots.

## Reporting

**Report** has four pages:

- **PRISMA 2020.** The flow diagram, as SVG, PNG or PDF. Winnow fills it from the
  review, and you add the counts it cannot know, such as records from other sources.
- **Statistics.** Progress per reviewer, and agreement (Cohen's kappa for two
  reviewers, Fleiss' for more).
- **Methods text.** A paragraph describing searches, deduplication and screening, with
  your numbers, ready to paste into a paper.
- **Exports.**
  - Records as CSV, Excel, RIS or BibTeX, filtered as you like.
  - Extracted data, in long or wide form.
  - A **full backup** of the review, which restores as a new review on this or any
    other Winnow (**Restore a backup** on the home page).

Owners and admins also see the **audit log**: who did what, and when.

## Notifications

The bell at the top tells you about:

- new conflicts to resolve;
- mentions in notes;
- invitations;
- finished or failed imports.

Opening a notification takes you to it. **Account → Notifications** turns on a daily
email digest of anything unread.

## Accessibility

Everything works from the keyboard, with a visible focus. Screen readers hear each
decision and the next record ("Included. Next record: …"). Controls are at least 44 px on
touch screens. Winnow follows your system's reduced-motion and colour-scheme settings.
docs/accessibility.md has the audit behind this.

## For instance administrators

**Instance admin** (in the sidebar, for administrators only) has three pages:

- **People.** Disable or re-enable an account, reset a lost authenticator, or sign
  someone out everywhere. Disabling keeps all of the person's work.
- **Settings.** Who may sign up, and the email Winnow gives Unpaywall.
- **Health.** The worker, the queue, the disk, the database size and the last backup.

Installing, updating and backing up the server itself: docs/deploy.md.

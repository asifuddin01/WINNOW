import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { authOptionsQuery } from "@/api/auth";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CloudOffIcon,
  HistoryIcon,
  KeyboardIcon,
  Maximize2Icon,
  Minimize2Icon,
  SearchIcon,
  SlidersHorizontalIcon,
  Undo2Icon,
} from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { fulltextSummaryQuery, pdfQuery, readable } from "@/api/fulltext";
import { keywordGroupsQuery, labelsQuery, projectQuery, reasonsQuery } from "@/api/projects";
import {
  postNote,
  progressQuery,
  putLabels,
  screeningKeys,
  type DecisionValue,
  type QueueSort,
  type Stage,
} from "@/api/screening";
import { SelectField } from "@/components/forms/SelectField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DecisionButtons,
  LabelChips,
  Notes,
  OthersDecisions,
  ReasonChips,
} from "@/features/screening/DecisionPanel";
import { FullTextPanel } from "@/features/fulltext/FullTextPanel";
import { buildMatchers } from "@/features/screening/highlight";
import { HistoryPanel, KeywordLegend, ShortcutList } from "@/features/screening/Panels";
import { RecordView } from "@/features/screening/RecordView";
import { SwipeCard } from "@/features/screening/SwipeCard";
import { useScreeningQueue } from "@/features/screening/use-queue";
import { useShortcuts } from "@/features/screening/use-shortcuts";
import { useVisibleTime } from "@/features/screening/use-visible-time";
import { DECIDED_TEXT } from "@/features/screening/wording";
import { StoppingBanner } from "@/features/ranking/StoppingBanner";
import { SuggestionBox } from "@/features/screening/SuggestionBox";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";

const SORTS: { value: QueueSort; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "random", label: "Random" },
  { value: "year", label: "Year, newest" },
  { value: "title", label: "Title A–Z" },
  { value: "added", label: "Import order" },
];

export interface ScreeningView {
  sort: QueueSort;
  q: string;
}

/**
 * Screening (guide 8.5, 8.8). The next record is always already held, so it appears the
 * moment a decision is made; the decision goes to the server behind it. At full text the
 * record's PDF is shown beside the decision, and the next record's PDF is fetched ahead.
 */
export function ScreeningPage({
  pid,
  stage,
  view,
  onViewChange,
}: {
  pid: string;
  stage: Stage;
  view: ScreeningView;
  onViewChange: (view: ScreeningView) => void;
}) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const { data: project } = useQuery(projectQuery(pid));
  const { data: groups = [] } = useQuery(keywordGroupsQuery(pid));
  const { data: allReasons = [] } = useQuery(reasonsQuery(pid));
  const { data: labels = [] } = useQuery(labelsQuery(pid));
  const { data: progress } = useQuery(progressQuery(pid, stage));
  const { data: options } = useQuery(authOptionsQuery);
  const fullText = stage === "full_text";
  const { data: fulltextSummary } = useQuery({
    ...fulltextSummaryQuery(pid),
    enabled: fullText,
  });

  const [focus, setFocus] = useState(false);
  const [highlightOn, setHighlightOn] = useState(true);
  const [hiddenGroups, setHiddenGroups] = useState<string[]>([]);
  const [sheet, setSheet] = useState<"filters" | "history" | "help" | "record" | null>(null);
  // What has been chosen for the record on screen; another record starts from its own.
  const [draft, setDraft] = useState<{ id?: string; reasons: string[]; open: boolean }>({
    reasons: [],
    open: false,
  });
  const [announcement, setAnnouncement] = useState("");
  const [typed, setTyped] = useState(view.q);
  const searchRef = useRef<HTMLInputElement>(null);
  const noteId = useId();

  const settings = project?.settings;
  const reasons = useMemo(
    () => allReasons.filter((reason) => reason.stage === stage || reason.stage === "both"),
    [allReasons, stage],
  );
  const reasonRequired =
    stage === "title_abstract"
      ? Boolean(settings?.require_reason_on_exclude_ta)
      : Boolean(settings?.require_reason_on_exclude_ft);

  const refreshProgress = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: screeningKeys.all(pid) });
  }, [pid, queryClient]);

  const queue = useScreeningQueue(pid, stage, view.sort, view.q);
  const current = queue.current;
  const takeTime = useVisibleTime(current?.id);

  // The next record's PDF, fetched while this one is read.
  const upcoming = queue.upcoming;
  useEffect(() => {
    const next = upcoming?.fulltext;
    if (!fullText || !upcoming || !next || !readable(next.scan_status)) return;
    // Only a head start: a failure here is met again, and shown, when the record opens.
    queryClient.query(pdfQuery(pid, upcoming.id, next.id)).catch(() => undefined);
  }, [fullText, upcoming, pid, queryClient]);

  const matchers = useMemo(
    () =>
      highlightOn ? buildMatchers(groups.filter((group) => !hiddenGroups.includes(group.id))) : [],
    [groups, hiddenGroups, highlightOn],
  );

  const currentId = current?.id;
  const ownDraft = draft.id !== undefined && draft.id === currentId;
  const savedReasons = current?.my_decision?.reason_ids;
  const reasonDraft = useMemo(
    () => (ownDraft ? draft.reasons : (savedReasons ?? [])),
    [ownDraft, draft.reasons, savedReasons],
  );
  const reasonsOpen = ownDraft && draft.open;
  const setReasonsOpen = useCallback(
    (open: boolean | ((was: boolean) => boolean)) => {
      setDraft((was) => {
        const mine = was.id === currentId;
        const reasons = mine ? was.reasons : (current?.my_decision?.reason_ids ?? []);
        const wasOpen = mine && was.open;
        return { id: currentId, reasons, open: typeof open === "function" ? open(wasOpen) : open };
      });
    },
    [currentId, current?.my_decision?.reason_ids],
  );

  // A refused decision offers Retry, which runs the latest `decide`.
  const retry = useRef<((decision: DecisionValue) => Promise<void>) | null>(null);
  const decide = useCallback(
    async (decision: DecisionValue) => {
      if (!current) return;
      if (decision === "exclude" && reasonRequired && reasonDraft.length === 0) {
        setReasonsOpen(true);
        setAnnouncement("Choose an exclusion reason, then exclude.");
        return;
      }
      const upcoming = queue.upcoming;
      // The queue shows the decision and the next record straight away; say so straight
      // away too, rather than after the server answers.
      const sent = queue.decide({ decision, reason_ids: reasonDraft }, takeTime());
      setAnnouncement(
        upcoming
          ? `${DECIDED_TEXT[decision]}. Next record: ${upcoming.title ?? "untitled"}.`
          : `${DECIDED_TEXT[decision]}.`,
      );
      toast(DECIDED_TEXT[decision], {
        id: "decision",
        duration: 2500,
        action: {
          label: "Undo",
          onClick: () => {
            void queue.undo().then(refreshProgress);
          },
        },
      });
      const result = await sent;
      if (!result.ok) {
        // Refused: the record is back on screen as it was.
        setAnnouncement(`Not saved: ${errorMessage(result.error)}`);
        toast.error(errorMessage(result.error), {
          id: "decision",
          action: { label: "Retry", onClick: () => void retry.current?.(decision) },
        });
        return;
      }
      refreshProgress();
    },
    [current, queue, reasonDraft, reasonRequired, takeTime, refreshProgress, setReasonsOpen],
  );

  useEffect(() => {
    retry.current = decide;
  }, [decide]);

  const toggleReason = useCallback(
    (id: string) => {
      if (!id) return;
      setDraft((was) => {
        const mine = was.id === currentId;
        const reasons = mine ? was.reasons : (current?.my_decision?.reason_ids ?? []);
        return {
          id: currentId,
          reasons: reasons.includes(id) ? reasons.filter((item) => item !== id) : [...reasons, id],
          open: mine && was.open,
        };
      });
    },
    [currentId, current?.my_decision?.reason_ids],
  );

  const toggleLabel = useCallback(
    (labelId: string) => {
      if (!current) return;
      const next = current.labels.includes(labelId)
        ? current.labels.filter((id) => id !== labelId)
        : [...current.labels, labelId];
      queue.update(current.id, { labels: next });
      putLabels(pid, current.id, next).catch((error: unknown) => {
        queue.update(current.id, { labels: current.labels });
        toast.error(errorMessage(error));
      });
    },
    [current, pid, queue],
  );

  const addNote = useCallback(
    async (body: string, visibility: "private" | "team") => {
      if (!current) return;
      try {
        const note = await postNote(pid, current.id, body, visibility);
        queue.update(current.id, { notes: [...current.notes, note] });
      } catch (error) {
        toast.error(errorMessage(error));
        throw error;
      }
    },
    [current, pid, queue],
  );

  const undo = useCallback(() => {
    if (!queue.canUndo) return;
    void queue.undo().then((record) => {
      setAnnouncement(record ? `Decision undone: ${record.title ?? "record"}.` : "");
      refreshProgress();
    });
  }, [queue, refreshProgress]);

  const shortcuts = useMemo(() => {
    const map: Record<string, () => void> = {
      i: () => void decide("include"),
      "1": () => {
        if (reasonsOpen) toggleReason(reasons[0]?.id ?? "");
        else void decide("include");
      },
      m: () => void decide("maybe"),
      "2": () => {
        if (reasonsOpen) toggleReason(reasons[1]?.id ?? "");
        else void decide("maybe");
      },
      e: () => void decide("exclude"),
      "3": () => {
        if (reasonsOpen) toggleReason(reasons[2]?.id ?? "");
        else void decide("exclude");
      },
      j: queue.next,
      ArrowRight: queue.next,
      k: queue.previous,
      ArrowLeft: queue.previous,
      r: () => {
        setReasonsOpen((open) => !open);
      },
      l: () => {
        if (isMobile) setSheet("record");
        document.getElementById("record-labels")?.querySelector("button")?.focus();
      },
      n: () => {
        if (isMobile) setSheet("record");
        document.getElementById(noteId)?.focus();
      },
      f: () => {
        setFocus((on) => !on);
      },
      h: () => {
        setHighlightOn((on) => !on);
      },
      "/": () => {
        if (isMobile) setSheet("filters");
        searchRef.current?.focus();
      },
      "?": () => {
        setSheet("help");
      },
      Escape: () => {
        setReasonsOpen(false);
      },
      "mod+z": undo,
    };
    // While the reasons are open, 4-9 toggle the rest of them.
    for (let number = 4; number <= 9; number++) {
      map[String(number)] = () => {
        const reason = reasons[number - 1];
        if (reasonsOpen && reason) toggleReason(reason.id);
      };
    }
    return map;
  }, [
    decide,
    queue.next,
    queue.previous,
    reasonsOpen,
    reasons,
    toggleReason,
    undo,
    isMobile,
    noteId,
    setReasonsOpen,
  ]);
  useShortcuts(shortcuts, sheet === null);

  const openFromHistory = useCallback(
    (recordId: string) => {
      setSheet(null);
      void queue.open(recordId);
    },
    [queue],
  );

  if (!project) return null;
  if (!project.permissions.includes("screen")) {
    return (
      <p className="mx-auto max-w-xl p-8 text-center text-muted-foreground">
        Viewers do not screen. Ask an admin of this review for the reviewer role.
      </p>
    );
  }

  const progressLine = progress && (
    <p className="text-sm" aria-live="off">
      <span className="font-semibold tabular-nums">{progress.screened.toLocaleString()}</span>
      <span className="text-muted-foreground">
        {" "}
        / {progress.total.toLocaleString()} screened by you
      </span>
      {progress.conflicts != null && progress.conflicts > 0 && (
        <>
          {" · "}
          <Link
            to="/p/$pid/conflicts"
            params={{ pid }}
            className="text-conflict underline-offset-2 hover:underline"
          >
            {progress.conflicts.toLocaleString()} conflict{progress.conflicts === 1 ? "" : "s"}
          </Link>
        </>
      )}
    </p>
  );

  const filters = (
    <div className="grid gap-4">
      <form
        className="grid gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          onViewChange({ ...view, q: typed.trim() });
        }}
      >
        <label htmlFor="screening-search" className="text-sm font-medium">
          Search <span className="font-normal text-muted-foreground">(/)</span>
        </label>
        <div className="flex gap-1.5">
          <Input
            id="screening-search"
            ref={searchRef}
            value={typed}
            placeholder='"night shift" year:2015.. label:rct'
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
          <Button type="submit" size="icon" variant="outline" aria-label="Search">
            <SearchIcon aria-hidden="true" />
          </Button>
        </div>
      </form>
      <SelectField
        label="Order"
        value={view.sort}
        options={SORTS}
        hint={
          view.sort !== "relevance"
            ? undefined
            : settings?.ranking_enabled
              ? "Most likely relevant first. One record in 20 is picked at random instead, so the model also learns from records it would rank low."
              : "Ranking is off for this review, so this is random order."
        }
        onChange={(sort) => {
          onViewChange({ ...view, sort });
        }}
      />
      <KeywordLegend
        groups={groups}
        hidden={hiddenGroups}
        enabled={highlightOn}
        onToggle={(id) => {
          setHiddenGroups((hidden) =>
            hidden.includes(id) ? hidden.filter((item) => item !== id) : [...hidden, id],
          );
        }}
      />
      {progress && (
        <dl className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-md bg-include-muted p-2">
            <dt>Included</dt>
            <dd className="text-base font-semibold tabular-nums">{progress.included}</dd>
          </div>
          <div className="rounded-md bg-maybe-muted p-2">
            <dt>Maybe</dt>
            <dd className="text-base font-semibold tabular-nums">{progress.maybe}</dd>
          </div>
          <div className="rounded-md bg-exclude-muted p-2">
            <dt>Excluded</dt>
            <dd className="text-base font-semibold tabular-nums">{progress.excluded}</dd>
          </div>
        </dl>
      )}
    </div>
  );

  const decisionPanel = current && (
    <div className="grid gap-5">
      <DecisionButtons current={current.my_decision?.decision} onDecide={(d) => void decide(d)} />
      <section aria-labelledby="reasons-heading" className="grid gap-2">
        <div className="flex items-center justify-between">
          <h3
            id="reasons-heading"
            className="text-xs font-semibold text-muted-foreground uppercase"
          >
            Exclusion reasons{reasonRequired ? " (required)" : ""}
          </h3>
          <button
            type="button"
            onClick={() => {
              setReasonsOpen((open) => !open);
            }}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
            aria-expanded={reasonsOpen}
          >
            {reasonsOpen ? "Numbers on (R)" : "R for numbers"}
          </button>
        </div>
        <ReasonChips
          reasons={reasons}
          selected={reasonDraft}
          onToggle={toggleReason}
          numbered={reasonsOpen}
        />
      </section>
      <section id="record-labels" aria-labelledby="labels-heading" className="grid gap-2">
        <h3 id="labels-heading" className="text-xs font-semibold text-muted-foreground uppercase">
          Labels (L)
        </h3>
        <LabelChips labels={labels} selected={current.labels} onToggle={toggleLabel} />
      </section>
      <section aria-labelledby="notes-heading" className="grid gap-2">
        <h3 id="notes-heading" className="text-xs font-semibold text-muted-foreground uppercase">
          Notes (N)
        </h3>
        <Notes key={current.id} notes={current.notes} onAdd={addNote} inputId={noteId} />
      </section>
      {settings?.llm_assist_enabled && options?.llm_available && (
        <SuggestionBox
          key={current.id}
          pid={pid}
          rid={current.id}
          stage={stage}
          provider={options.llm_provider}
        />
      )}
      <OthersDecisions item={current} reasons={reasons} />
    </div>
  );

  const nav = (
    <div className="flex items-center justify-between gap-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={queue.previous}
        disabled={queue.position === 0}
      >
        <ChevronLeftIcon aria-hidden="true" /> Previous <span className="sr-only">(K)</span>
      </Button>
      <div className="flex items-center gap-1">
        <Button type="button" variant="ghost" size="sm" onClick={undo} disabled={!queue.canUndo}>
          <Undo2Icon aria-hidden="true" /> Undo
        </Button>
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={queue.next} disabled={!current}>
        Next <span className="sr-only">(J)</span> <ChevronRightIcon aria-hidden="true" />
      </Button>
    </div>
  );

  const record = queue.loading ? (
    <div className="grid gap-3" aria-busy="true">
      <Skeleton className="h-9 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-48 w-full" />
    </div>
  ) : current && fullText ? (
    <div className="grid gap-4">
      <RecordView
        item={current}
        matchers={matchers}
        showScore={Boolean(settings?.ranking_enabled)}
        compact
      />
      <FullTextPanel
        key={current.id}
        pid={pid}
        record={current}
        matchers={matchers}
        canScreen
        openAccess={Boolean(fulltextSummary?.open_access)}
        onChange={(fulltext) => {
          queue.update(current.id, { fulltext });
        }}
        onNotRetrievable={() => {
          setAnnouncement("Marked not retrievable. Next record.");
          queue.drop(current.id);
          refreshProgress();
        }}
      />
    </div>
  ) : current ? (
    <RecordView
      item={current}
      matchers={matchers}
      focus={focus}
      showScore={Boolean(settings?.ranking_enabled)}
    />
  ) : (
    <div className="grid justify-items-center gap-3 rounded-xl border border-dashed border-input p-10 text-center">
      <p className="text-lg font-semibold">Nothing left for you to screen here.</p>
      <p className="max-w-md text-sm text-muted-foreground">
        {view.q
          ? "No undecided records match this search."
          : "Every record assigned to you has your decision. You can go back through your history to change any of them."}
      </p>
      {view.q && (
        <Button
          variant="outline"
          onClick={() => {
            setTyped("");
            onViewChange({ ...view, q: "" });
          }}
        >
          Clear the search
        </Button>
      )}
    </div>
  );

  const waitingBanner = queue.waiting > 0 && (
    <p
      role="status"
      className="flex items-center gap-2 rounded-md bg-maybe-muted px-3 py-2 text-sm"
    >
      <CloudOffIcon className="size-4" aria-hidden="true" />
      {queue.waiting} decision{queue.waiting === 1 ? "" : "s"} waiting to sync. They will be sent
      when the connection is back.
    </p>
  );

  const stoppingBanner = settings?.ranking_enabled && <StoppingBanner pid={pid} stage={stage} />;

  const liveRegion = (
    <p aria-live="polite" className="sr-only">
      {announcement}
    </p>
  );

  const toolbar = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight">
          {fullText ? "Full-text screening" : "Title and abstract screening"}
        </h1>
        {progressLine}
      </div>
      <div className="flex items-center gap-1">
        {!isMobile && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={focus}
            onClick={() => {
              setFocus((on) => !on);
            }}
          >
            {focus ? <Minimize2Icon aria-hidden="true" /> : <Maximize2Icon aria-hidden="true" />}
            Focus <span className="sr-only">mode (F)</span>
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setSheet("history");
          }}
        >
          <HistoryIcon aria-hidden="true" /> History
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Keyboard shortcuts (?)"
          onClick={() => {
            setSheet("help");
          }}
        >
          <KeyboardIcon aria-hidden="true" />
        </Button>
      </div>
    </div>
  );

  const sheets = (
    <Sheet
      open={sheet !== null}
      onOpenChange={(open) => {
        if (!open) setSheet(null);
      }}
    >
      <SheetContent
        side={isMobile ? "bottom" : "right"}
        className={cn("overflow-y-auto", isMobile && "max-h-[85dvh]")}
      >
        <SheetHeader>
          <SheetTitle>
            {sheet === "history"
              ? "Your decisions"
              : sheet === "help"
                ? "Keyboard shortcuts"
                : sheet === "filters"
                  ? "Search and order"
                  : "Reasons, labels and notes"}
          </SheetTitle>
          <SheetDescription>
            {sheet === "history"
              ? "Open one to look at it again or change your decision."
              : sheet === "help"
                ? "They never fire while you are typing."
                : sheet === "filters"
                  ? "What to screen next, and in which order."
                  : "For the record on screen."}
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          {sheet === "history" && <HistoryPanel pid={pid} stage={stage} onOpen={openFromHistory} />}
          {sheet === "help" && <ShortcutList />}
          {sheet === "filters" && filters}
          {sheet === "record" && decisionPanel}
        </div>
      </SheetContent>
    </Sheet>
  );

  if (isMobile) {
    return (
      <div className="grid gap-3 px-3 pt-3 pb-40">
        {toolbar}
        {waitingBanner}
        {stoppingBanner}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSheet("filters");
            }}
          >
            <SlidersHorizontalIcon aria-hidden="true" /> Search and order
          </Button>
        </div>
        {current && !fullText ? (
          <SwipeCard
            onSwipe={(d) => void decide(d)}
            header={
              <p className="text-center text-xs text-muted-foreground select-none">
                ← exclude · swipe up here for maybe · include →
              </p>
            }
          >
            {record}
          </SwipeCard>
        ) : (
          record
        )}
        {liveRegion}
        {sheets}
        {current && (
          <div className="fixed inset-x-0 bottom-0 z-30 grid gap-2 border-t border-border bg-background/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur">
            <DecisionButtons
              compact
              current={current.my_decision?.decision}
              onDecide={(d) => void decide(d)}
            />
            <div className="flex items-center justify-between gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={queue.previous}
                disabled={queue.position === 0}
              >
                <ChevronLeftIcon aria-hidden="true" /> Back
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSheet("record");
                }}
              >
                Reasons, labels, notes
              </Button>
              <Button variant="ghost" size="sm" onClick={undo} disabled={!queue.canUndo}>
                <Undo2Icon aria-hidden="true" /> Undo
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (focus) {
    return (
      <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-6 md:px-8">
        {toolbar}
        {waitingBanner}
        {stoppingBanner}
        {record}
        {current && (
          <div className="sticky bottom-0 grid gap-3 border-t border-border bg-background/95 py-3 backdrop-blur">
            <DecisionButtons
              current={current.my_decision?.decision}
              onDecide={(d) => void decide(d)}
            />
            {reasonsOpen && (
              <ReasonChips
                reasons={reasons}
                selected={reasonDraft}
                onToggle={toggleReason}
                numbered
              />
            )}
            {nav}
          </div>
        )}
        {liveRegion}
        {sheets}
      </div>
    );
  }

  return (
    <div className="grid w-full gap-4 px-4 py-6 md:px-6">
      {toolbar}
      {waitingBanner}
      {stoppingBanner}
      <div
        className={cn(
          "grid gap-6 md:grid-cols-[1fr_18rem]",
          fullText ? "lg:grid-cols-[1fr_19rem]" : "lg:grid-cols-[15rem_1fr_19rem]",
        )}
      >
        {!fullText && (
          <aside aria-label="Search and filters" className="hidden lg:block">
            {filters}
          </aside>
        )}
        <div className="grid min-w-0 content-start gap-4">
          <div className={cn(!fullText && "lg:hidden")}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSheet("filters");
              }}
            >
              <SlidersHorizontalIcon aria-hidden="true" /> Search and order
            </Button>
          </div>
          {record}
          {current && nav}
        </div>
        <aside aria-label="Your decision" className="md:sticky md:top-4 md:self-start">
          {decisionPanel}
        </aside>
      </div>
      {liveRegion}
      {sheets}
    </div>
  );
}

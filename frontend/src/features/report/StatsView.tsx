import { useQuery } from "@tanstack/react-query";
import { EyeOffIcon } from "lucide-react";

import { errorMessage } from "@/api/client";
import { statsQuery, type Agreement, type StageStats } from "@/api/reporting";
import { FormAlert } from "@/components/forms/FormAlert";
import { ScrollRegion } from "@/components/layout/ScrollRegion";
import { Skeleton } from "@/components/ui/skeleton";

const STAGES: Record<StageStats["stage"], string> = {
  title_abstract: "Title and abstract",
  full_text: "Full text",
};

const n = (value: number) => value.toLocaleString();
const percent = (value: number | null) => (value === null ? "—" : `${(value * 100).toFixed(1)}%`);
const kappa = (value: number | null) => (value === null ? "Not calculable" : value.toFixed(2));

export function StatsView({ pid }: { pid: string }) {
  const { data, error, isPending } = useQuery(statsQuery(pid));
  if (isPending) return <Skeleton className="h-96 w-full rounded-xl" aria-busy="true" />;
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;

  return (
    <div className="grid gap-6">
      {data.blind && (
        <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm">
          <EyeOffIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Blind mode is on, so you see your own screening only. Agreement between reviewers is shown
          to those allowed to see everyone&apos;s decisions.
        </p>
      )}
      {data.stages.map((stage) => (
        <Stage key={stage.stage} stage={stage} />
      ))}
    </div>
  );
}

function Stage({ stage }: { stage: StageStats }) {
  const name = STAGES[stage.stage];
  const headingId = `stage-${stage.stage}`;
  const done = stage.records === 0 ? 0 : Math.round((stage.decided / stage.records) * 100);
  return (
    <section
      aria-labelledby={headingId}
      className="grid gap-4 rounded-xl border border-border bg-card p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={headingId} className="text-lg font-medium">
          {name}
        </h2>
        <p className="text-sm text-muted-foreground">
          {n(stage.decided)} of {n(stage.records)} records decided
          {stage.conflicts !== null && ` · ${n(stage.conflicts)} in conflict`}
        </p>
      </div>
      <div
        role="progressbar"
        aria-label={`${name}: records decided`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={done}
        aria-valuetext={`${done}%`}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${done}%` }} />
      </div>

      {stage.reviewers.length > 0 ? (
        <ScrollRegion label={`${name}: progress per reviewer`}>
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">{name}: progress per reviewer</caption>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Reviewer
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Decided
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Included
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Excluded
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Maybe
                </th>
                <th scope="col" className="py-2 pl-3 text-right font-medium">
                  Median per record
                </th>
              </tr>
            </thead>
            <tbody>
              {stage.reviewers.map((reviewer) => (
                <tr key={reviewer.user_id} className="border-t border-border">
                  <th scope="row" className="py-2 pr-3 text-left font-normal">
                    {reviewer.name}
                    {reviewer.mine && <span className="text-muted-foreground"> (you)</span>}
                  </th>
                  <td className="px-3 py-2 text-right tabular-nums">{n(reviewer.decided)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{n(reviewer.included)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{n(reviewer.excluded)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{n(reviewer.maybe)}</td>
                  <td className="py-2 pl-3 text-right tabular-nums">
                    {reviewer.median_seconds === null ? "—" : `${reviewer.median_seconds} s`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      ) : (
        <p className="text-sm text-muted-foreground">No decisions at this stage yet.</p>
      )}

      {stage.per_day.length > 0 && <PerDay name={name} days={stage.per_day} />}
      {stage.agreement && <AgreementTable name={name} agreement={stage.agreement} />}
    </section>
  );
}

/** Decisions per day: bars for the eye, the same numbers as a table for everyone else. */
// The server sends the last 60 days that had decisions (PER_DAY in services/reporting).
const WINDOW = 60;

/** Every day of the window, oldest first, with none where nothing was decided. */
function lastDays(days: StageStats["per_day"], today: Date = new Date()): StageStats["per_day"] {
  const counts = new Map(days.map((day) => [day.day, day.decisions]));
  return Array.from({ length: WINDOW }, (_, index) => {
    const date = new Date(today);
    date.setUTCDate(date.getUTCDate() - (WINDOW - 1 - index));
    const day = date.toISOString().slice(0, 10);
    return { day, decisions: counts.get(day) ?? 0 };
  });
}

function PerDay({ name, days }: { name: string; days: StageStats["per_day"] }) {
  const window = lastDays(days);
  const most = Math.max(...window.map((day) => day.decisions), 1);
  return (
    <div className="grid gap-2">
      <h3 className="text-sm font-medium">Decisions per day, last {WINDOW} days</h3>
      <div className="grid gap-1" aria-hidden="true">
        <div className="flex h-20 items-end gap-px border-b border-border">
          {window.map((day) => (
            <div
              key={day.day}
              title={`${day.day}: ${day.decisions}`}
              className="flex-1 rounded-t-sm bg-primary/70"
              style={{
                height: day.decisions ? `${Math.max(4, (day.decisions / most) * 100)}%` : 0,
              }}
            />
          ))}
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{window[0]?.day}</span>
          <span>Today</span>
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">Show as a table</summary>
        <table className="mt-2 text-sm">
          <caption className="sr-only">{name}: decisions per day</caption>
          <thead>
            <tr>
              <th scope="col" className="pr-6 text-left font-medium">
                Day
              </th>
              <th scope="col" className="text-right font-medium">
                Decisions
              </th>
            </tr>
          </thead>
          <tbody>
            {days.map((day) => (
              <tr key={day.day}>
                <td className="pr-6">{day.day}</td>
                <td className="text-right tabular-nums">{n(day.decisions)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function AgreementTable({ name, agreement }: { name: string; agreement: Agreement }) {
  if (agreement.pairs.length === 0 && agreement.fleiss_kappa === null) {
    return (
      <p className="text-sm text-muted-foreground">
        Agreement appears once two reviewers have decided the same records.
      </p>
    );
  }
  return (
    <div className="grid gap-2">
      <h3 className="text-sm font-medium">Agreement between reviewers</h3>
      <ScrollRegion label={`${name}: agreement between reviewers`}>
        <table className="w-full min-w-[34rem] text-sm">
          <caption className="sr-only">{name}: agreement between reviewers</caption>
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">
                Reviewers
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Records both decided
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Agreement
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Cohen&apos;s κ
              </th>
              <th scope="col" className="py-2 pl-3 font-medium">
                Strength
              </th>
            </tr>
          </thead>
          <tbody>
            {agreement.pairs.map((pair) => (
              <tr key={`${pair.reviewer_a}|${pair.reviewer_b}`} className="border-t border-border">
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {pair.reviewer_a} and {pair.reviewer_b}
                </th>
                <td className="px-3 py-2 text-right tabular-nums">{n(pair.records)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{percent(pair.percent)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{kappa(pair.kappa)}</td>
                <td className="py-2 pl-3 capitalize">{pair.band ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
      {agreement.raters >= 3 && (
        <p className="text-sm">
          Fleiss&apos; κ over the {n(agreement.fleiss_records)} records decided by{" "}
          {agreement.raters} reviewers: <strong>{kappa(agreement.fleiss_kappa)}</strong>
          {agreement.fleiss_band && ` (${agreement.fleiss_band})`}.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Kappa corrects agreement for chance; bands follow Landis and Koch (1977). It cannot be
        calculated when two people share no records or both used a single answer throughout.
      </p>
    </div>
  );
}

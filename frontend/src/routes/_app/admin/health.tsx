import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import type { ReactNode } from "react";

import { healthQuery } from "@/api/admin";
import { errorMessage } from "@/api/client";
import { FormAlert } from "@/components/forms/FormAlert";
import { Skeleton } from "@/components/ui/skeleton";
import { fileSize, timeAgo } from "@/lib/format";

export const Route = createFileRoute("/_app/admin/health")({
  component: HealthPage,
  staticData: { title: "Health" },
});

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2 rounded-xl border border-border bg-card p-4" aria-label={title}>
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

function State({ ok, children }: { ok: boolean; children: ReactNode }) {
  const Icon = ok ? CircleCheckIcon : CircleAlertIcon;
  return (
    <p className="flex items-center gap-2 text-base font-semibold">
      <Icon className={ok ? "size-5 text-include" : "size-5 text-destructive"} aria-hidden="true" />
      {children}
    </p>
  );
}

const TWO_DAYS_MS = 2 * 24 * 3600 * 1000;

/** A nightly backup less than two days old: one missed night is not yet alarming. */
function recent(iso: string): boolean {
  return Date.now() - new Date(iso).getTime() < TWO_DAYS_MS;
}

/** Guide 8.18: queue, worker, disk, database and the last backup; looked at every 15 s. */
function HealthPage() {
  const { data, error, isPending } = useQuery(healthQuery);
  if (isPending) return <Skeleton className="h-64 w-full rounded-xl" aria-busy="true" />;
  if (error) return <FormAlert>{errorMessage(error)}</FormAlert>;
  const report = data.queue.worker_report;
  const disk = data.disk;
  const used = disk ? Math.round((disk.used_bytes / disk.total_bytes) * 100) : 0;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card title="Worker">
        <State ok={data.queue.worker_alive}>
          {data.queue.worker_alive ? "Running" : "Not responding"}
        </State>
        <p className="text-sm text-muted-foreground">
          {data.queue.worker_alive
            ? `${report.j_complete ?? 0} jobs done, ${report.j_failed ?? 0} failed, ${report.j_ongoing ?? 0} running since it started.`
            : "Imports, scans and exports wait until it is back. Check `docker compose ps worker`."}
        </p>
      </Card>
      <Card title="Queue">
        <p className="text-base font-semibold">{data.queue.waiting.toLocaleString()} waiting</p>
        <p className="text-sm text-muted-foreground">Jobs not yet started.</p>
      </Card>
      <Card title="Last backup">
        {data.last_backup ? (
          <>
            <State ok={recent(data.last_backup.at)}>{timeAgo(data.last_backup.at)}</State>
            <p className="text-sm break-all text-muted-foreground">
              {data.last_backup.file}
              {data.last_backup.size_bytes != null && ` · ${fileSize(data.last_backup.size_bytes)}`}
            </p>
          </>
        ) : (
          <>
            <State ok={false}>None recorded</State>
            <p className="text-sm text-muted-foreground">
              Set up the nightly backup described in docs/deploy.md.
            </p>
          </>
        )}
      </Card>
      <Card title="Disk">
        {disk ? (
          <>
            <State ok={used < 90}>{fileSize(disk.free_bytes)} free</State>
            <div
              role="progressbar"
              aria-label="Disk used"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={used}
              aria-valuetext={`${used}% used`}
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div className="h-full rounded-full bg-primary" style={{ width: `${used}%` }} />
            </div>
            <p className="text-sm text-muted-foreground">
              {used}% of {fileSize(disk.total_bytes)} used where files are kept.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Files are kept in an S3 bucket.</p>
        )}
      </Card>
      <Card title="Database">
        <p className="text-base font-semibold">{fileSize(data.database_bytes)}</p>
        <p className="text-sm text-muted-foreground">
          {data.users.toLocaleString()} people, {data.reviews.toLocaleString()} reviews,{" "}
          {data.records.toLocaleString()} records.
        </p>
      </Card>
      <Card title="Version">
        <p className="text-base font-semibold">Winnow {data.version}</p>
      </Card>
    </div>
  );
}

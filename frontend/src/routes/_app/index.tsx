import { useQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArchiveRestoreIcon, LibraryBigIcon, PlusIcon, UsersIcon } from "lucide-react";

import { projectsQuery, type ProjectSummary } from "@/api/projects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { REVIEW_TYPES, ROLES, STATUSES } from "@/features/projects/wording";
import { timeAgo } from "@/lib/format";

export const Route = createFileRoute("/_app/")({
  component: MyReviews,
  staticData: { title: "My reviews" },
});

function MyReviews() {
  const { data, isPending } = useQuery(projectsQuery);
  const reviews = data?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">My reviews</h1>
          <p className="mt-1 text-muted-foreground">
            Systematic, scoping and rapid reviews you lead or take part in.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to="/restore">
              <ArchiveRestoreIcon aria-hidden="true" /> Restore a backup
            </Link>
          </Button>
          <Button asChild>
            <Link to="/new">
              <PlusIcon aria-hidden="true" /> New review
            </Link>
          </Button>
        </div>
      </div>

      {isPending ? (
        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {[0, 1].map((key) => (
            <li key={key}>
              <Skeleton className="h-32 w-full rounded-xl" />
            </li>
          ))}
        </ul>
      ) : reviews.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {reviews.map((review) => (
            <li key={review.id}>
              <ReviewCard review={review} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewCard({ review }: { review: ProjectSummary }) {
  return (
    <Link
      to="/p/$pid"
      params={{ pid: review.id }}
      className="flex h-full flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-ring focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold">{review.title}</h2>
        <Badge variant="secondary">{ROLES[review.role]}</Badge>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        {REVIEW_TYPES[review.review_type]} · {STATUSES[review.status]}
      </p>
      <p className="mt-auto flex items-center gap-3 pt-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <UsersIcon className="size-3.5" aria-hidden="true" />
          {review.member_count} {review.member_count === 1 ? "member" : "members"}
        </span>
        <span>Active {timeAgo(review.last_activity_at)}</span>
      </p>
    </Link>
  );
}

function EmptyState() {
  return (
    <section
      aria-labelledby="no-reviews"
      className="mt-8 flex flex-col items-center rounded-xl border border-dashed border-input px-6 py-16 text-center"
    >
      <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <LibraryBigIcon className="size-6" aria-hidden="true" />
      </span>
      <h2 id="no-reviews" className="text-lg font-medium">
        No reviews yet
      </h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        Start a review to set out your question, criteria and team. Anything you are invited to
        joins this list once you accept.
      </p>
      <Button asChild className="mt-6">
        <Link to="/new">
          <PlusIcon aria-hidden="true" /> New review
        </Link>
      </Button>
    </section>
  );
}

import { createFileRoute } from "@tanstack/react-router";
import { LibraryBigIcon } from "lucide-react";

export const Route = createFileRoute("/_app/")({
  component: MyReviews,
  staticData: { title: "My reviews" },
});

function MyReviews() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">My reviews</h1>
      <p className="mt-1 text-muted-foreground">
        Systematic, scoping and rapid reviews you lead or take part in.
      </p>
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
          When you create a review or accept an invitation, it appears here with its screening
          progress and conflicts.
        </p>
      </section>
    </div>
  );
}

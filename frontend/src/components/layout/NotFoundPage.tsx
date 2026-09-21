import { Link } from "@tanstack/react-router";
import { ArrowLeftIcon, SearchXIcon } from "lucide-react";

import { useInShell } from "@/components/layout/shell-context";
import { StandalonePage } from "@/components/layout/StandalonePage";
import { Button } from "@/components/ui/button";

function NotFoundPanel() {
  return (
    <section
      aria-labelledby="not-found-title"
      className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center px-4 py-16 text-center"
    >
      <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <SearchXIcon className="size-6" aria-hidden="true" />
      </span>
      <h1 id="not-found-title" className="text-xl font-semibold tracking-tight">
        Page not found
      </h1>
      <p className="mt-2 text-muted-foreground">
        This address does not match any page. It may have moved, or the link may be mistyped.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">
          <ArrowLeftIcon aria-hidden="true" />
          Back to my reviews
        </Link>
      </Button>
    </section>
  );
}

export function NotFoundPage() {
  return useInShell() ? (
    <NotFoundPanel />
  ) : (
    <StandalonePage>
      <NotFoundPanel />
    </StandalonePage>
  );
}

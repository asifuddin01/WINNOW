import { Link } from "@tanstack/react-router";
import { ArrowLeftIcon, SearchXIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useInShell } from "@/components/layout/shell-context";
import { StandalonePage } from "@/components/layout/StandalonePage";
import { Button } from "@/components/ui/button";

interface NotFoundProps {
  title?: string;
  detail?: string;
  /** The router passes its own props when this is a route's notFoundComponent. */
  data?: unknown;
}

function NotFoundPanel({ title, detail }: NotFoundProps) {
  const { t } = useTranslation();
  return (
    <section
      aria-labelledby="not-found-title"
      className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center px-4 py-16 text-center"
    >
      <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <SearchXIcon className="size-6" aria-hidden="true" />
      </span>
      <h1 id="not-found-title" className="text-xl font-semibold tracking-tight">
        {title ?? t("notFound.title")}
      </h1>
      <p className="mt-2 text-muted-foreground">{detail ?? t("notFound.body")}</p>
      <Button asChild className="mt-6">
        <Link to="/">
          <ArrowLeftIcon aria-hidden="true" />
          {t("notFound.back")}
        </Link>
      </Button>
    </section>
  );
}

export function NotFoundPage(props: NotFoundProps) {
  const panel = <NotFoundPanel {...props} />;
  return useInShell() ? panel : <StandalonePage>{panel}</StandalonePage>;
}
